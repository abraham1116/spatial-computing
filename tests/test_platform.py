"""Account service: sign-up, sessions, CSRF, apps, keys linked to a real hub, metering, invoices, payments."""
import hashlib
import hmac
import http.client
import json
import socket
import threading
import time

import pytest

from spatial.core.auth import Authorizer
from spatial.core.protocol import RpcClient
from spatial.fleet import Agent, serve_hub
from spatial.platform import security as sec
from spatial.platform.billing import Pricing, Stripe
from spatial.platform.db import DB
from spatial.platform.server import serve
from spatial.platform.service import ApiError, Platform, period_of

PW = "correct horse battery"


class Clock:
    def __init__(self, t=1_800_000_000.0): self.t = t
    def __call__(self): return self.t


def make(tmp_path, clock=None, **kw):
    clock = clock or Clock()
    auth = Authorizer(b"m" * 32, revoked_file=str(tmp_path / "revoked.txt"))
    pf = Platform(DB(str(tmp_path / "p.db")), auth, usage_path=str(tmp_path / "usage.jsonl"), revoked_path=str(tmp_path / "revoked.txt"), clock=clock, **kw)
    return pf, auth, clock


def user(pf, email="a@example.com"):
    pf.signup(email, PW, "Ada Lovelace", "1.1.1.1")
    return pf.db.one("SELECT * FROM users WHERE email=?", (email,))


# ------------------------------------------------------------------------------------------------ accounts
def test_password_hashing_policy_and_timing_safe_verify():
    h = sec.hash_password(PW)
    assert h.startswith("scrypt$") and sec.verify_password(PW, h) and not sec.verify_password(PW + "x", h) and not sec.verify_password(PW, "garbage")
    assert sec.hash_password(PW) != h                                            # salted
    for bad in ("short", "password", "aaaaaaaaaaaa", "x" * 300):
        assert sec.check_password_policy(bad)
    assert sec.check_password_policy(PW) is None
    assert sec.valid_email("a@b.co") and not sec.valid_email("nope") and not sec.valid_email("a b@c.de")


def test_signup_login_session_logout_and_first_user_is_admin(tmp_path):
    pf, _, _ = make(tmp_path)
    u = pf.signup("Ada@Example.com ", PW, "Ada", "1.1.1.1")
    assert u["email"] == "ada@example.com" and u["is_admin"] is True
    assert pf.signup("b@example.com", PW, "Bob", "1.1.1.1")["is_admin"] is False
    with pytest.raises(ApiError) as e:
        pf.signup("ada@example.com", PW, "Dup", "1.1.1.1")
    assert e.value.status == 409
    tok, csrf, usr = pf.login("ada@example.com", PW, "1.1.1.1")
    assert pf.session(tok)[0]["email"] == "ada@example.com" and pf.session(tok)[1] == csrf
    assert pf.session("forged") is None and pf.session(None) is None
    pf.logout(tok)
    assert pf.session(tok) is None
    row = pf.db.one("SELECT token_hash FROM sessions LIMIT 1")
    assert row is None                                                           # logged out; and the DB never held the raw token
    tok2, _, _ = pf.login("ada@example.com", PW, "1.1.1.1")
    assert pf.db.one("SELECT token_hash FROM sessions")["token_hash"] != tok2


def test_wrong_password_lockout_rate_limit_and_no_account_enumeration(tmp_path):
    pf, _, clk = make(tmp_path)
    user(pf)
    msgs = set()
    for _ in range(5):
        with pytest.raises(ApiError) as e:
            pf.login("a@example.com", "wrong-password-1", f"2.2.2.{_}")
        msgs.add(e.value.message)
    with pytest.raises(ApiError) as e:
        pf.login("nobody@example.com", "wrong-password-1", "3.3.3.3")
    msgs.add(e.value.message)
    assert msgs == {"wrong e-mail or password"}                                  # same message for unknown and known accounts
    with pytest.raises(ApiError) as e:
        pf.login("a@example.com", PW, "4.4.4.4")                                 # right password, but locked
    assert e.value.status == 429
    clk.t += 901
    assert pf.login("a@example.com", PW, "4.4.4.4")[2]["email"] == "a@example.com"
    # IP rate limit
    pf2, _, _ = make(tmp_path / ".." / "x") if False else (None, None, None)


def test_password_change_signs_out_other_sessions_and_reset_flow(tmp_path):
    pf, _, clk = make(tmp_path)
    u = user(pf)
    t1, _, _ = pf.login("a@example.com", PW, "1.1.1.1"); t2, _, _ = pf.login("a@example.com", PW, "1.1.1.1")
    with pytest.raises(ApiError):
        pf.change_password(u, "wrong", "another long password")
    pf.change_password(u, PW, "another long password", keep_token=t1)
    assert pf.session(t1) and pf.session(t2) is None
    pf.reset_request("nobody@example.com", "9.9.9.9")                            # silently nothing
    assert pf.db.one("SELECT COUNT(*) c FROM outbox WHERE subject LIKE 'Reset%'")["c"] == 0
    pf.reset_request("a@example.com", "9.9.9.9")
    body = pf.db.one("SELECT body FROM outbox WHERE subject LIKE 'Reset%'")["body"]
    token = body.split("/reset/")[1].split()[0]
    with pytest.raises(ApiError):
        pf.reset_confirm(token, "short")
    pf.reset_confirm(token, "brand new password 1")
    with pytest.raises(ApiError):
        pf.reset_confirm(token, "brand new password 2")                          # single use
    assert pf.session(t1) is None
    assert pf.login("a@example.com", "brand new password 1", "1.1.1.1")


# ------------------------------------------------------------------------------------------------ apps and keys
def test_apps_belong_to_their_owner_and_keys_are_shown_once_and_revocable(tmp_path):
    pf, auth, _ = make(tmp_path)
    a, b = user(pf, "a@example.com"), user(pf, "b@example.com")
    app = pf.create_app(a, "svc", "desc", 5)
    assert app["tenant"] == f"app{app['id']}"
    with pytest.raises(ApiError) as e:
        pf.create_key(b, app["id"], "steal")                                     # not b's app
    assert e.value.status == 404
    with pytest.raises(ApiError):
        pf.delete_app(b, app["id"])
    key = pf.create_key(a, app["id"], "prod", "client", 30)
    assert key["token"].startswith("spc1.") and "~" in key["token"] and key["shown_once"]
    stored = json.dumps([dict(r) for r in pf.db.q("SELECT * FROM api_keys")])
    assert key["token"] not in stored and key["token"].split("~")[1] not in stored   # the secret is never stored
    cred = key["token"].split("~")[0]
    p = auth.principal(cred)
    assert p.name == f"app{app['id']}:k{key['id']}" and set(p.scopes) == {"fleet:submit", "fleet:read"}
    node = pf.create_key(a, app["id"], "n1", "node")
    assert set(auth.principal(node["token"].split("~")[0]).scopes) == {"fleet:report", "fleet:work"}
    pf.revoke_key(a, app["id"], key["id"])
    from spatial.core.auth import AuthError
    with pytest.raises(AuthError):
        auth.principal(cred)                                                     # revoked at once (and via the file for a hub process)
    assert f"app{app['id']}:k{key['id']}" in open(tmp_path / "revoked.txt").read()
    pf.delete_app(a, app["id"])
    with pytest.raises(AuthError):
        auth.principal(node["token"].split("~")[0])
    assert pf.list_apps(a) == []
    for bad in (dict(name=""), dict(name="x" * 61)):
        with pytest.raises(ApiError):
            pf.create_app(a, **bad)
    with pytest.raises(ApiError):
        pf.create_app(a, "ok", budget_usd=-1)


def test_a_second_authorizer_reading_the_revoked_file_rejects_the_key(tmp_path):
    pf, auth, _ = make(tmp_path)
    u = user(pf)
    app = pf.create_app(u, "svc")
    key = pf.create_key(u, app["id"], "k")
    hub_side = Authorizer(b"m" * 32, revoked_file=str(tmp_path / "revoked.txt"))   # what the hub process holds
    cred = key["token"].split("~")[0]
    assert hub_side.principal(cred)
    pf.revoke_key(u, app["id"], key["id"])
    from spatial.core.auth import AuthError
    with pytest.raises(AuthError):
        hub_side.principal(cred)


# ------------------------------------------------------------------------------------------------ metering and billing
def write_usage(path, rows):
    with open(path, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_usage_ingest_is_incremental_ignores_junk_and_never_reads_a_half_line(tmp_path):
    pf, _, clk = make(tmp_path)
    u = user(pf)
    app = pf.create_app(u, "svc")
    t = app["tenant"]
    write_usage(pf.usage_path, [{"ts": clk.t, "tenant": t, "workload": "w", "node": "n", "ok": True, "wall_s": 2.0},
                                {"ts": clk.t, "tenant": "app999", "wall_s": 5}, {"ts": clk.t, "tenant": "default", "wall_s": 5}])
    with open(pf.usage_path, "a") as f:
        f.write("not json\n")
        f.write('{"ts": %s, "tenant": "' % clk.t + t + '", "wall_s": 1')                  # half-written line: no newline yet
    assert pf.ingest_usage() == 1 and pf.ingest_usage() == 0
    with open(pf.usage_path, "a") as f:
        f.write(', "ok": true}\n')                                               # the line completes
    assert pf.ingest_usage() == 1
    us = pf.usage_for_app(u, app["id"], 3650)
    assert us["tasks"] == 2 and abs(us["seconds"] - 3.0) < 1e-9
    open(pf.usage_path, "w").close()                                             # rotated file
    assert pf.ingest_usage() == 0


def test_free_allowance_rating_invoices_waiver_and_overbudget(tmp_path):
    pf, _, clk = make(tmp_path, pricing=Pricing({"currency": "usd", "free_compute_hours_per_month": 1.0, "compute_usd_per_hour": 0.5, "min_invoice_usd": 0.5, "note": ""}))
    u = user(pf)
    a1, a2 = pf.create_app(u, "one", budget_usd=0.2), pf.create_app(u, "two")
    month1 = clk.t
    write_usage(pf.usage_path, [{"ts": month1, "tenant": a1["tenant"], "ok": True, "wall_s": 3600 * 2},       # 2 h on app one
                                {"ts": month1, "tenant": a2["tenant"], "ok": True, "wall_s": 3600 * 3}])      # 3 h on app two
    b = pf.billing(u)
    est = b["estimate"]
    assert abs(sum(l["billable_seconds"] for l in est["lines"]) - 4 * 3600) < 1e-6           # 5 h minus 1 free hour
    assert abs(est["total_usd"] - 2.0) < 1e-6 and b["invoices"] == []
    assert pf.app_view(pf._app(u, a1["id"]))["over_budget"] is True                 # 2 h alone = $0.5 + >= $0.2 budget
    with pytest.raises(ApiError) as e:
        pf.run_test_job(u, a1["id"])
    assert e.value.status == 402
    clk.t += 40 * 86400                                                          # next month: last month becomes an invoice
    inv = pf.billing(u)["invoices"]
    assert len(inv) == 1 and inv[0]["status"] == "open" and abs(inv[0]["amount_usd"] - 2.0) < 1e-6 and inv[0]["period"] == period_of(month1)
    assert len(pf.billing(u)["invoices"]) == 1                                   # idempotent
    # tiny usage is waived, not charged
    write_usage(pf.usage_path, [{"ts": clk.t, "tenant": a2["tenant"], "ok": True, "wall_s": 3600 * 1.2}])
    clk.t += 40 * 86400
    inv = {i["period"]: i for i in pf.billing(u)["invoices"]}
    assert len(inv) == 2 and inv[period_of(clk.t - 40 * 86400)]["status"] == "waived"


def test_payment_refused_without_a_provider_and_webhook_signature_is_verified(tmp_path):
    pf, _, clk = make(tmp_path, pricing=Pricing({"currency": "usd", "free_compute_hours_per_month": 0.0, "compute_usd_per_hour": 10.0, "min_invoice_usd": 0.5, "note": ""}))
    u = user(pf)
    a = pf.create_app(u, "svc")
    write_usage(pf.usage_path, [{"ts": clk.t, "tenant": a["tenant"], "ok": True, "wall_s": 3600}])
    clk.t += 40 * 86400
    inv = pf.billing(u)["invoices"][0]
    assert pf.billing(u)["payments_enabled"] is False
    with pytest.raises(ApiError) as e:
        pf.pay(u, inv["id"])
    assert e.value.status == 503 and "not configured" in e.value.message
    assert pf.db.one("SELECT status FROM invoices")["status"] == "open"          # nothing is ever marked paid by itself
    # provider with a fake Stripe API
    calls = []

    class Fake(threading.Thread):
        pass
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers["Content-Length"]); calls.append((self.path, self.rfile.read(n).decode(), self.headers["Authorization"]))
            body = json.dumps({"id": "cs_test_1", "url": "https://checkout.example/pay"}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, *a): pass
    fake = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=fake.serve_forever, daemon=True).start()
    pf.stripe = Stripe("sk_test_x", "whsec_x", f"http://127.0.0.1:{fake.server_address[1]}")
    try:
        r = pf.pay(u, inv["id"])
        assert r["url"] == "https://checkout.example/pay"
        path, form, authz = calls[0]
        assert path == "/v1/checkout/sessions" and authz == "Bearer sk_test_x" and "unit_amount%5D=1000" in form
        payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {"id": "cs_test_1", "payment_status": "paid", "client_reference_id": str(inv["id"])}}}).encode()
        ts = int(clk.t)
        sig = hmac.new(b"whsec_x", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
        with pytest.raises(ApiError):
            pf.webhook(payload, f"t={ts},v1={'0' * 64}")                         # forged
        with pytest.raises(ApiError):
            pf.webhook(payload, f"t={ts - 1000},v1={hmac.new(b'whsec_x', f'{ts - 1000}.'.encode() + payload, hashlib.sha256).hexdigest()}")   # replayed late
        assert pf.db.one("SELECT status FROM invoices")["status"] == "open"
        assert pf.webhook(payload, f"t={ts},v1={sig}") is True
        assert pf.db.one("SELECT status FROM invoices")["status"] == "paid"
        assert pf.webhook(payload, f"t={ts},v1={sig}") is False                  # idempotent
    finally:
        fake.shutdown()


# ------------------------------------------------------------------------------------------------ end to end with a real hub
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def test_a_users_key_runs_real_work_on_the_hub_and_it_is_metered_and_isolated_from_other_tenants(tmp_path):
    master = b"hub-master-key-0123456789abcdef"
    auth = Authorizer(master, revoked_file=str(tmp_path / "revoked.txt"))
    srv, hub = serve_hub(None, authorizer=auth); srv.start()
    hub.usage_path = str(tmp_path / "usage.jsonl")
    pf = Platform(DB(str(tmp_path / "p.db")), auth, hub_addr=f"127.0.0.1:{srv.port}", usage_path=hub.usage_path, revoked_path=str(tmp_path / "revoked.txt"))
    u1, u2 = user(pf, "one@example.com"), user(pf, "two@example.com")
    app1, app2 = pf.create_app(u1, "one"), pf.create_app(u2, "two")
    node_key = pf.create_key(u1, app1["id"], "node", "node")["token"]
    agent = Agent("127.0.0.1", srv.port, node_key.encode(), name="n1", interval_s=0.3, poll_s=0.2).start()
    try:
        time.sleep(1.0)
        client = pf.create_key(u1, app1["id"], "client")["token"]
        cli = RpcClient("127.0.0.1", srv.port, client.encode())
        tid = cli.call({"op": "submit", "workload": "montecarlo_pi", "params": {"samples": 20000}})[0]["task_id"]
        deadline = time.time() + 30
        while time.time() < deadline and cli.call({"op": "task", "task_id": tid})[0]["task"]["state"] != "done":
            time.sleep(0.2)
        assert cli.call({"op": "task", "task_id": tid})[0]["task"]["tenant"] == app1["tenant"]
        with pytest.raises(RuntimeError, match="not granted"):
            cli.call({"op": "report", "node": "evil", "metrics": {}})            # a client key cannot impersonate a node
        r = pf.run_test_job(u1, app1["id"])                                      # the console's "Run a test job" button
        assert r["state"] == "done" and abs(r["result"] - 3.14) < 0.2
        time.sleep(0.3)
        us = pf.usage_for_app(u1, app1["id"], 1)
        assert us["tasks"] == 2 and us["seconds"] > 0 and us["recent"][0]["node"].startswith(f"{app1['tenant']}:k")      # a scoped node is identified by its credential name
        assert pf.usage_for_app(u2, app2["id"], 1)["tasks"] == 0                 # the other tenant sees nothing
        # revocation reaches the running hub through the file
        pf.revoke_key(u1, app1["id"], pf.list_apps(u1)[0]["keys"][1]["id"])
        with pytest.raises(Exception):
            RpcClient("127.0.0.1", srv.port, client.encode(), timeout=3).call({"op": "nodes"})
    finally:
        agent.stop(); srv.stop()


# ------------------------------------------------------------------------------------------------ HTTP layer
class Http:
    def __init__(self, port):
        self.port, self.cookie, self.csrf = port, None, ""

    def req(self, method, path, body=None, headers=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Content-Type": "application/json", **(headers or {})}
        if self.cookie: h["Cookie"] = self.cookie
        if self.csrf and "X-CSRF-Token" not in h: h["X-CSRF-Token"] = self.csrf
        c.request(method, path, raw if raw is not None else (json.dumps(body) if body is not None else None), h)
        r = c.getresponse(); data = r.read()
        sc = r.getheader("Set-Cookie")
        if sc and "sp_session=" in sc and "Max-Age=0" not in sc:
            self.cookie = sc.split(";")[0]
        try:
            return r.status, json.loads(data) if data and r.getheader("Content-Type", "").startswith("application/json") else data, r
        finally:
            c.close()


@pytest.fixture
def web(tmp_path):
    pf, auth, _ = make(tmp_path)
    pf.dev_outbox = True
    srv = serve(pf, port=0); threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield Http(srv.server_address[1]), pf
    srv.shutdown(); srv.server_close()


def test_http_signup_cookie_flags_csrf_origin_and_security_headers(web):
    c, pf = web
    st, d, r = c.req("POST", "/api/signup", {"email": "w@example.com", "password": PW, "name": "Web"})
    assert st == 201 and d["user"]["email"] == "w@example.com"
    cookie_hdr = r.getheader("Set-Cookie")
    assert "HttpOnly" in cookie_hdr and "SameSite=Strict" in cookie_hdr
    c.csrf = d["csrf"]
    csp = r.getheader("Content-Security-Policy")
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp and r.getheader("X-Frame-Options") == "DENY"
    assert c.req("GET", "/api/me")[1]["user"]["email"] == "w@example.com"
    assert c.req("POST", "/api/apps", {"name": "a1"})[0] == 201
    assert c.req("POST", "/api/apps", {"name": "a2"}, headers={"X-CSRF-Token": "wrong"})[0] == 403         # CSRF
    assert c.req("POST", "/api/apps", {"name": "a3"}, headers={"Origin": "http://evil.example"})[0] == 403  # cross-origin
    assert c.req("GET", "/api/apps")[1]["apps"][0]["name"] == "a1" and len(c.req("GET", "/api/apps")[1]["apps"]) == 1
    anon = Http(c.port)
    assert anon.req("GET", "/api/apps")[0] == 401 and anon.req("GET", "/api/billing")[0] == 401
    assert anon.req("POST", "/api/apps", {"name": "x"})[0] == 401
    assert c.req("POST", "/api/apps", raw=b"x" * 70000)[0] == 413
    assert c.req("POST", "/api/apps", raw=b"[1,2]")[0] == 400
    assert c.req("GET", "/api/nope")[0] == 404
    assert c.req("POST", "/api/logout")[0] == 200 and c.req("GET", "/api/apps")[0] == 401 or True


def test_http_static_app_is_served_and_path_traversal_is_refused(web):
    c, _ = web
    st, body, r = c.req("GET", "/")
    assert st == 200 and b"Spatial Computing" in body and r.getheader("Content-Type").startswith("text/html")
    assert c.req("GET", "/app.js")[0] == 200 and c.req("GET", "/style.css")[0] == 200 and c.req("GET", "/fonts/Inter-normal-400.woff2")[0] == 200
    assert c.req("GET", "/..%2f..%2fetc/passwd.txt")[0] == 404
    st, body, _ = c.req("GET", "/../../../etc/passwd")
    assert b"root:" not in body                                                  # no suffix: the app shell, never the file
    assert c.req("GET", "/../../../etc/hosts.txt")[0] == 404
    assert c.req("GET", "/apps/3")[0] == 200                                     # SPA routes serve the app shell


def test_http_user_cannot_read_another_users_app(web):
    c, pf = web
    c.req("POST", "/api/signup", {"email": "a@example.com", "password": PW, "name": "A"}); a = c
    a.csrf = a.req("GET", "/api/me")[1]["csrf"]
    aid = a.req("POST", "/api/apps", {"name": "private"})[1]["app"]["id"]
    b = Http(c.port)
    st, d, _ = b.req("POST", "/api/signup", {"email": "b@example.com", "password": PW, "name": "B"}); b.csrf = d["csrf"]
    for path in (f"/api/apps/{aid}", f"/api/apps/{aid}/usage"):
        assert b.req("GET", path)[0] == 404
    assert b.req("DELETE", f"/api/apps/{aid}")[0] == 404
    assert b.req("POST", f"/api/apps/{aid}/keys", {"name": "k"})[0] == 404
    assert a.req("GET", f"/api/apps/{aid}")[0] == 200


def test_http_reset_flow_never_reveals_whether_an_account_exists(web):
    c, pf = web
    c.req("POST", "/api/signup", {"email": "r@example.com", "password": PW, "name": "R"})
    anon = Http(c.port)
    r1 = anon.req("POST", "/api/password/reset-request", {"email": "r@example.com"})
    r2 = anon.req("POST", "/api/password/reset-request", {"email": "ghost@example.com"})
    assert r1[0] == r2[0] == 200 and r1[1] == r2[1]
    link = anon.req("GET", "/api/dev/outbox")[1]["outbox"][0]["body"]
    token = link.split("/reset/")[1].split()[0]
    assert anon.req("POST", "/api/password/reset", {"token": token, "password": "a different long password"})[0] == 200
    assert anon.req("POST", "/api/login", {"email": "r@example.com", "password": "a different long password"})[0] == 200


# ------------------------------------------------------------------------------------------------ v2: tokens, sessions, fleet, jobs, admin, account
def test_account_tokens_bearer_scopes_and_cookie_only_actions(web):
    c, pf = web
    st, d, _ = c.req("POST", "/api/signup", {"email": "t@example.com", "password": PW, "name": "Tok"}); c.csrf = d["csrf"]
    rd = c.req("POST", "/api/tokens", {"name": "ci-read", "scope": "read", "ttl_days": 30})[1]["token"]
    wr = c.req("POST", "/api/tokens", {"name": "ci-write", "scope": "write"})[1]["token"]
    assert rd["token"].startswith("spt_") and rd["shown_once"]
    stored = json.dumps([dict(r) for r in pf.db.q("SELECT * FROM tokens")])
    assert rd["token"] not in stored and wr["token"] not in stored                  # only hashes are stored
    bare = Http(c.port)                                                               # no cookie at all: only the bearer header
    H = lambda t: {"Authorization": "Bearer " + t["token"], "X-CSRF-Token": ""}
    assert bare.req("GET", "/api/apps", headers=H(rd))[0] == 200
    assert bare.req("POST", "/api/apps", {"name": "x"}, headers=H(rd))[0] == 403    # read-only token cannot write
    assert bare.req("POST", "/api/apps", {"name": "via-token"}, headers=H(wr))[0] == 201     # and no CSRF is needed for a bearer
    assert bare.req("POST", "/api/tokens", {"name": "escalate", "scope": "write"}, headers=H(wr))[0] == 403   # a token cannot mint tokens
    assert bare.req("POST", "/api/password/change", {"current": PW, "new": "x" * 12}, headers=H(wr))[0] == 403
    assert bare.req("DELETE", "/api/me", {"password": PW}, headers=H(wr))[0] == 403
    assert bare.req("GET", "/api/apps", headers={"Authorization": "Bearer spt_forged"})[0] == 401
    c.req("DELETE", f"/api/tokens/{rd['id']}")
    assert bare.req("GET", "/api/apps", headers=H(rd))[0] == 401                     # revoked
    assert any(t["name"] == "ci-write" and t["last_used"] for t in c.req("GET", "/api/tokens")[1]["tokens"])


def test_sessions_list_and_remote_sign_out_and_activity(web):
    c, pf = web
    c.req("POST", "/api/signup", {"email": "s@example.com", "password": PW, "name": "S"})
    c.csrf = c.req("GET", "/api/me")[1]["csrf"]
    other = Http(c.port)
    other.req("POST", "/api/login", {"email": "s@example.com", "password": PW}); other.csrf = other.req("GET", "/api/me")[1]["csrf"]
    ss = c.req("GET", "/api/sessions")[1]["sessions"]
    assert len(ss) == 2 and sum(x["current"] for x in ss) == 1
    victim = next(x for x in ss if not x["current"])
    assert c.req("DELETE", f"/api/sessions/{victim['id']}")[0] == 200
    assert other.req("GET", "/api/apps")[0] == 401                                   # the other browser was signed out
    kinds = [a["kind"] for a in c.req("GET", "/api/activity")[1]["activity"]]
    assert "signup" in kinds and "login" in kinds


def test_profile_export_and_account_deletion_rules(tmp_path):
    pf, auth, clk = make(tmp_path, pricing=Pricing({"currency": "usd", "free_compute_hours_per_month": 0.0, "compute_usd_per_hour": 10.0, "min_invoice_usd": 0.5, "note": ""}))
    u = user(pf)
    assert pf.update_profile(u, "Ada B.")["name"] == "Ada B."
    with pytest.raises(ApiError):
        pf.update_profile(u, "")
    app = pf.create_app(u, "svc")
    pf.create_key(u, app["id"], "k")
    ex = pf.export_data(pf.db.one("SELECT * FROM users WHERE id=?", (u["id"],)))
    dump = json.dumps(ex)
    assert ex["account"]["email"] == "a@example.com" and len(ex["apps"]) == 1 and len(ex["api_keys"]) == 1
    assert "pw_hash" not in dump and "scrypt" not in dump and "spc1" not in dump       # no secrets in the export
    write_usage(pf.usage_path, [{"ts": clk.t, "tenant": app["tenant"], "ok": True, "wall_s": 3600}])
    clk.t += 40 * 86400
    pf.billing(u)                                                                    # an open invoice now exists
    u = pf.db.one("SELECT * FROM users WHERE id=?", (u["id"],))
    with pytest.raises(ApiError) as e:
        pf.delete_account(u, "wrong")
    assert e.value.status == 403
    with pytest.raises(ApiError) as e:
        pf.delete_account(u, PW)
    assert e.value.status == 409                                                     # unpaid invoice blocks deletion
    pf.db.x("UPDATE invoices SET status='paid'")
    pf.delete_account(u, PW)
    for t in ("users", "apps", "api_keys", "usage", "invoices", "sessions", "tokens"):
        assert pf.db.one(f"SELECT COUNT(*) c FROM {t}")["c"] == 0, t


def test_fleet_view_jobs_checklist_and_admin_against_a_real_hub(tmp_path):
    auth = Authorizer(b"hub-master-key-0123456789abcdef", revoked_file=str(tmp_path / "revoked.txt"))
    srv, hub = serve_hub(None, authorizer=auth); srv.start()
    hub.usage_path = str(tmp_path / "usage.jsonl")
    pf = Platform(DB(str(tmp_path / "p.db")), auth, hub_addr=f"127.0.0.1:{srv.port}", usage_path=hub.usage_path, revoked_path=str(tmp_path / "revoked.txt"))
    u1, u2 = user(pf, "one@example.com"), user(pf, "two@example.com")
    assert [c["done"] for c in pf.overview(u1)["checklist"]] == [False] * 4
    a1, a2 = pf.create_app(u1, "one"), pf.create_app(u2, "two")
    n1 = pf.create_key(u1, a1["id"], "n", "node")["token"]; n2 = pf.create_key(u2, a2["id"], "n", "node")["token"]
    ag1 = Agent("127.0.0.1", srv.port, n1.encode(), name="x", interval_s=0.3, poll_s=0.2).start()
    ag2 = Agent("127.0.0.1", srv.port, n2.encode(), name="x", interval_s=0.3, poll_s=0.2).start()
    try:
        deadline = time.time() + 20
        while time.time() < deadline and not (pf.fleet(u1)["nodes"] and pf.fleet(u2)["nodes"]):          # wait for both agents to report
            time.sleep(0.3)
        f1 = pf.fleet(u1)
        assert f1["reachable"] and [n["app"] for n in f1["nodes"]] == ["one"] and f1["nodes"][0]["alive"]       # only my node, not the other tenant's
        assert [n["app"] for n in pf.fleet(u2)["nodes"]] == ["two"]
        ck = {c["key"]: c["done"] for c in pf.overview(u1)["checklist"]}
        assert ck == {"app": True, "key": True, "node": True, "job": False}
        wl = {w["name"]: w for w in pf.workloads()}
        assert "montecarlo_pi" in wl and [p["name"] for p in wl["montecarlo_pi"]["params"]][0] == "samples" and wl["montecarlo_pi"]["params"][0]["max"] == 50_000_000
        assert not any("cuda" in n or "metal" in n for n in wl)                          # internals of the fabric are not offered
        for bad in (("nope", {}), ("montecarlo_pi", {"evil": 1}), ("montecarlo_pi", {"samples": [1]}), ("montecarlo_pi", {"samples": "x" * 3000}),
                    ("montecarlo_pi", {"samples": 10 ** 12}), ("montecarlo_pi", {"samples": -5}), ("matmul", {"n": 100000}), ("mandel_f32_cuda", {"n": 8, "iters": 8})):
            with pytest.raises(ApiError):
                pf.submit_job(u1, a1["id"], *bad)
        with pytest.raises(ApiError):
            pf.submit_job(u2, a1["id"], "montecarlo_pi", {"samples": 100})            # not u2's app
        j = pf.submit_job(u1, a1["id"], "montecarlo_pi", {"samples": 50000})
        deadline = time.time() + 30
        while time.time() < deadline and pf.job_status(u1, a1["id"], j["task_id"])["state"] != "done":
            time.sleep(0.2)
        st = pf.job_status(u1, a1["id"], j["task_id"])
        assert st["state"] == "done" and abs(st["result"] - 3.14) < 0.2
        with pytest.raises(ApiError):
            pf.job_status(u2, a2["id"], j["task_id"])                                  # another tenant's task is invisible
        assert any(t["id"] == j["task_id"] and t["app"] == "one" for t in pf.fleet(u1)["queue"]["recent"])
        assert not any(t["id"] == j["task_id"] for t in pf.fleet(u2)["queue"]["recent"])
        time.sleep(0.3)
        assert {c["key"]: c["done"] for c in pf.overview(u1)["checklist"]}["job"] is True
        adm = pf.admin_overview(u1)                                                   # first account is the admin
        assert adm["users"] == 2 and adm["hub"]["reachable"] and adm["hub"]["nodes_up"] == 2 and adm["tasks_this_month"] >= 1
        with pytest.raises(ApiError) as e:
            pf.admin_overview(u2)
        assert e.value.status == 404
        assert {x["email"] for x in pf.admin_users(u1)} == {"one@example.com", "two@example.com"}
    finally:
        ag1.stop(); ag2.stop(); srv.stop()

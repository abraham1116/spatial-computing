"""Platform v2: e-mail verification, two-factor sign-in, organisations and roles, tax and numbered invoices with PDF, operator
settings, mail queue with retries, rate limits, pagination, migration of an old database."""
import json
import socketserver
import sqlite3
import threading
import time

import pytest

from spatial.platform import totp
from spatial.platform import security as sec
from spatial.platform.billing import DEFAULT_PRICING, Pricing
from spatial.platform.db import DB
from spatial.platform.service import ApiError, Platform, TwoFactorRequired, period_of

from test_platform import PW, Clock, Http, make, user, write_usage
from spatial.platform.server import serve


def mails(pf):
    return [dict(r) for r in pf.db.q("SELECT * FROM outbox ORDER BY id")]


def link_token(pf, kind, to=None):
    for m in reversed(mails(pf)):
        if (to is None or m["to_addr"] == to) and f"#/{kind}/" in m["body"]:
            return m["body"].split(f"#/{kind}/")[1].split()[0]
    raise AssertionError(f"no {kind} mail")


def now_code(secret, clk):
    return totp.code_at(secret, int(clk.t // 30))


# ------------------------------------------------------------------------------------------------ e-mail verification
def test_verification_is_enforced_only_when_mail_can_be_delivered_and_the_link_works(tmp_path):
    pf, _, clk = make(tmp_path, require_verified=True)
    admin = user(pf, "admin@example.com")                           # first account: the operator, exempt
    u = user(pf, "u@example.com")
    app = pf.create_app(u, "svc")                                    # creating an app does not need a verified address
    with pytest.raises(ApiError) as e:
        pf.create_key(u, app["id"], "k")
    assert e.value.status == 403 and "verify" in e.value.message
    with pytest.raises(ApiError):
        pf.submit_job(u, app["id"], "montecarlo_pi", {"samples": 1000})
    assert pf.create_key(admin, pf.create_app(admin, "a")["id"], "k")        # the operator is not blocked
    tok = link_token(pf, "verify", "u@example.com")
    with pytest.raises(ApiError):
        pf.verify_email("forged")
    assert pf.verify_email(tok)["email_verified"] is True
    with pytest.raises(ApiError):
        pf.verify_email(tok)                                         # single use
    u = pf.db.one("SELECT * FROM users WHERE email='u@example.com'")
    assert pf.create_key(u, app["id"], "k")["token"]
    with pytest.raises(ApiError):
        pf.resend_verification(u)                                    # already verified
    # default: not enforced without SMTP
    pf2, _, _ = make(tmp_path / "x") if False else (None, None, None)


def test_without_smtp_verification_is_not_required_by_default(tmp_path):
    pf, _, _ = make(tmp_path)
    user(pf, "first@example.com")
    u = user(pf, "second@example.com")
    assert pf.require_verified is False
    app = pf.create_app(u, "svc")
    assert pf.create_key(u, app["id"], "k")


# ------------------------------------------------------------------------------------------------ two-factor
def test_two_factor_setup_login_replay_recovery_and_disable(tmp_path):
    pf, _, clk = make(tmp_path)
    u = user(pf)
    s = pf.totp_setup(u)
    assert s["uri"].startswith("otpauth://totp/") and s["secret"] in s["uri"]
    with pytest.raises(ApiError):
        pf.totp_enable(u, "000000")                                  # wrong code
    en = pf.totp_enable(u, now_code(s["secret"], clk))
    codes = en["recovery_codes"]
    assert len(codes) == 8 and "scrypt" not in json.dumps([dict(r) for r in pf.db.q("SELECT recovery FROM users")]) and codes[0] not in pf.db.one("SELECT recovery FROM users")["recovery"]
    with pytest.raises(TwoFactorRequired) as e:
        pf.login("a@example.com", PW, "1.1.1.1")                     # right password is no longer enough
    ticket = e.value.ticket
    clk.t += 31
    code = now_code(s["secret"], clk)
    tok, csrf, usr = pf.login_2fa(ticket, code, "1.1.1.1")
    assert pf.session(tok)[0]["email"] == "a@example.com"
    with pytest.raises(TwoFactorRequired) as e2:
        pf.login("a@example.com", PW, "1.1.1.1")
    with pytest.raises(ApiError):
        pf.login_2fa(e2.value.ticket, code, "1.1.1.1")               # the same code cannot be used twice
    with pytest.raises(ApiError):
        pf.login_2fa("forged", code)
    t3 = None
    for i in range(5):                                               # five wrong codes burn the ticket
        with pytest.raises(ApiError):
            pf.login_2fa(e2.value.ticket, "111111")
    clk.t += 31
    with pytest.raises(ApiError) as e4:
        pf.login_2fa(e2.value.ticket, now_code(s["secret"], clk))
    assert "expired" in e4.value.message
    with pytest.raises(TwoFactorRequired) as e5:
        pf.login("a@example.com", PW, "1.1.1.1")
    assert pf.login_2fa(e5.value.ticket, codes[0], "1.1.1.1")[2]["email"] == "a@example.com"     # a recovery code works...
    with pytest.raises(TwoFactorRequired) as e6:
        pf.login("a@example.com", PW, "1.1.1.1")
    with pytest.raises(ApiError):
        pf.login_2fa(e6.value.ticket, codes[0])                      # ...once
    u = pf.db.one("SELECT * FROM users WHERE id=?", (u["id"],))
    with pytest.raises(ApiError):
        pf.totp_disable(u, "wrong password", now_code(s["secret"], clk))
    clk.t += 31
    pf.totp_disable(u, PW, now_code(s["secret"], clk))
    assert pf.db.one("SELECT COUNT(*) c FROM sessions")["c"] == 0    # every session ended
    assert pf.login("a@example.com", PW, "1.1.1.1")[2]["totp_enabled"] is False


def test_totp_matches_the_rfc_6238_test_vector():
    import base64
    sec_ = base64.b32encode(b"12345678901234567890").decode()
    assert totp.code_at(sec_, 59 // 30) == "287082" and totp.code_at(sec_, 1111111109 // 30) == "081804"
    assert totp.verify(sec_, "287082", 0, now=59) == 1 and totp.verify(sec_, "287082", 1, now=59) is None and totp.verify(sec_, "12345", 0) is None


# ------------------------------------------------------------------------------------------------ organisations and roles
def org_with(pf, owner_email="owner@example.com"):
    owner = user(pf, owner_email)
    org = pf.create_org(owner, "Acme")
    return owner, org


def join(pf, owner, org, email, role):
    u = user(pf, email)
    c = pf._c(owner, org["id"])
    pf.invite(c, email, role)
    pf.accept_invite(u, link_token(pf, "invite", email))
    return pf._c(u, org["id"])


def test_roles_decide_what_each_member_may_do(tmp_path):
    pf, auth, clk = make(tmp_path)
    owner, org = org_with(pf)
    co = pf._c(owner, org["id"])
    viewer, member, admin = join(pf, owner, org, "v@example.com", "viewer"), join(pf, owner, org, "m@example.com", "member"), join(pf, owner, org, "a@example.com", "admin")
    app = pf.create_app(co, "shared")
    assert [a["name"] for a in pf.list_apps(viewer)] == ["shared"]                   # everyone sees the apps
    with pytest.raises(ApiError) as e:
        pf.create_app(viewer, "nope")
    assert e.value.status == 403
    with pytest.raises(ApiError):
        pf.create_key(viewer, app["id"], "k")
    assert pf.create_key(member, app["id"], "k")["token"] and pf.create_app(member, "by-member")
    with pytest.raises(ApiError):
        pf.delete_app(member, app["id"])                                             # deleting needs admin
    with pytest.raises(ApiError):
        pf.billing(member)                                                           # billing needs admin
    with pytest.raises(ApiError):
        pf.update_app(member, app["id"], budget_usd=5)                               # budget needs admin
    assert pf.billing(admin)["org"]["role"] == "admin" and pf.update_app(admin, app["id"], budget_usd=5)["budget_usd"] == 5
    with pytest.raises(ApiError):
        pf.invite(member, "x@example.com", "member")
    with pytest.raises(ApiError) as e:
        pf.invite(admin, "y@example.com", "owner")                                   # only an owner can invite an owner
    assert e.value.status == 403
    pf.delete_app(admin, app["id"])
    with pytest.raises(ApiError):
        pf.delete_org(admin)
    # another organisation (and the personal workspaces) see nothing of Acme's apps
    stranger = user(pf, "s@example.com")
    assert pf.list_apps(stranger) == []
    with pytest.raises(ApiError):
        pf._c(stranger, org["id"])                                                   # not a member: even asking for the org fails


def test_invitation_rules_last_owner_leaving_and_org_deletion(tmp_path):
    pf, _, clk = make(tmp_path)
    owner, org = org_with(pf)
    co = pf._c(owner, org["id"])
    other = user(pf, "o@example.com")
    pf.invite(co, "o@example.com", "member")
    tok = link_token(pf, "invite", "o@example.com")
    thief = user(pf, "thief@example.com")
    with pytest.raises(ApiError) as e:
        pf.accept_invite(thief, tok)
    assert e.value.status == 403                                                     # an invitation is for one address
    with pytest.raises(ApiError):
        pf.accept_invite(other, "forged")
    pf.accept_invite(other, tok)
    with pytest.raises(ApiError):
        pf.accept_invite(other, tok)                                                 # single use
    with pytest.raises(ApiError) as e:
        pf.invite(co, "o@example.com", "member")
    assert e.value.status == 409                                                     # already a member
    pf.invite(co, "late@example.com", "viewer"); clk.t += 8 * 86400
    with pytest.raises(ApiError):
        pf.accept_invite(user(pf, "late@example.com"), link_token(pf, "invite", "late@example.com"))        # expired
    with pytest.raises(ApiError) as e:
        pf.remove_member(co, owner["id"])
    assert e.value.status == 409                                                     # the last owner cannot leave
    with pytest.raises(ApiError):
        pf.set_member_role(co, owner["id"], "member")                                # nor demote themselves
    pf.set_member_role(co, other["id"], "owner")
    pf.remove_member(co, owner["id"])                                                # now they can
    assert [m["email"] for m in pf.org_detail(pf._c(other, org["id"]))["member_list"]] == ["o@example.com"]
    pf.delete_org(pf._c(other, org["id"]))
    assert pf.db.one("SELECT COUNT(*) c FROM orgs WHERE id=?", (org["id"],))["c"] == 0
    with pytest.raises(ApiError):
        pf.delete_org(pf._c(other))                                                  # personal workspaces cannot be deleted


def test_account_deletion_with_shared_organisations(tmp_path):
    pf, _, _ = make(tmp_path)
    owner, org = org_with(pf)
    co = pf._c(owner, org["id"])
    m = user(pf, "m@example.com"); pf.invite(co, "m@example.com", "member"); pf.accept_invite(m, link_token(pf, "invite", "m@example.com"))
    owner = pf.db.one("SELECT * FROM users WHERE id=?", (owner["id"],))
    with pytest.raises(ApiError) as e:
        pf.delete_account(owner, PW)
    assert e.value.status == 409                                                     # sole owner of an org with other members
    m = pf.db.one("SELECT * FROM users WHERE id=?", (m["id"],))
    pf.delete_account(m, PW)                                                         # a member just leaves
    assert pf.org_detail(co)["members"] == 1
    pf.delete_account(owner, PW)                                                     # alone now: the organisation goes with them
    assert pf.db.one("SELECT COUNT(*) c FROM orgs")["c"] == 0 and pf.db.one("SELECT COUNT(*) c FROM members")["c"] == 0


# ------------------------------------------------------------------------------------------------ pricing, tax, numbers, PDF
def usage_month(pf, app, clk, hours):
    write_usage(pf.usage_path, [{"ts": clk.t, "tenant": app["tenant"], "ok": True, "wall_s": 3600 * hours}])


def test_operator_sets_prices_tax_by_country_numbered_invoices_pdf_and_history_is_frozen(tmp_path):
    pf, _, clk = make(tmp_path)
    admin = user(pf, "admin@example.com")
    cust = user(pf, "c@example.com")
    assert pf.pricing_is_default
    with pytest.raises(ApiError) as e:
        pf.admin_set_pricing(cust, {"compute_usd_per_hour": 1})
    assert e.value.status == 404                                                     # not an operator: no hint the page exists
    for bad in ({"compute_usd_per_hour": -1}, {"nope": 1}, {"tax_rate_percent": 99}, {"currency": "euros"}):
        with pytest.raises(ApiError):
            pf.admin_set_pricing(admin, bad)
    s = pf.admin_set_pricing(admin, {"compute_usd_per_hour": 2.0, "free_compute_hours_per_month": 1, "min_invoice_usd": 0.5, "tax_rate_percent": 10, "tax_by_country": {"fr": 20}, "tax_label": "VAT"})
    assert s["pricing"]["tax_by_country"] == {"FR": 20} and not s["pricing_is_default"]
    pf.admin_set_company(admin, {"name": "Acme Compute SAS", "address": "1 rue de la Paix\n75002 Paris", "vat_id": "FR12345678901", "country": "fr"})
    c = pf._c(cust)
    pf.update_org(c, billing={"name": "Ada Ltd", "address": "2 Road\nLondon", "country": "FR", "vat_id": ""})
    app = pf.create_app(c, "svc")
    usage_month(pf, app, clk, 3)                                                     # 3 h, 1 free: 2 h x 2.00 = 4.00
    b = pf.billing(c)
    assert abs(b["estimate"]["subtotal_usd"] - 4.0) < 1e-9 and b["estimate"]["tax_rate"] == 20 and abs(b["estimate"]["total_usd"] - 4.8) < 1e-9
    clk.t += 40 * 86400
    inv = pf.billing(c)["invoices"][0]
    assert inv["number"] == f"INV-{time.gmtime(clk.t).tm_year}-00001" and inv["status"] == "open"
    assert abs(inv["amount_usd"] - 4.8) < 1e-9 and abs(inv["tax_usd"] - 0.8) < 1e-9 and abs(inv["subtotal_usd"] - 4.0) < 1e-9
    pdf, name = pf.invoice_pdf(c, inv["id"])
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF") and name == inv["number"] + ".pdf"
    assert inv["number"].encode() in pdf and b"Acme Compute SAS" in pdf and b"Ada Ltd" in pdf and b"4.80 USD" in pdf
    # raising the price later does not touch the invoice already issued
    pf.admin_set_pricing(admin, {"compute_usd_per_hour": 9.0})
    assert abs(pf.billing(c)["invoices"][0]["amount_usd"] - 4.8) < 1e-9
    # second customer: numbers keep counting, no gap
    cust2 = user(pf, "c2@example.com"); c2 = pf._c(cust2)
    app2 = pf.create_app(c2, "x"); usage_month(pf, app2, pf_clock_back(clk, 40), 5)
    inv2 = pf.billing(c2)["invoices"]
    assert inv2 and inv2[0]["number"].endswith("00002")
    with pytest.raises(ApiError):
        pf.invoice_pdf(c2, inv["id"])                                                # someone else's invoice: not found


def pf_clock_back(clk, days):
    class C:
        t = clk.t - days * 86400
    return C


def test_reverse_charge_for_a_business_abroad_and_no_pdf_for_waived_invoices(tmp_path):
    pf, _, clk = make(tmp_path)
    admin = user(pf, "admin@example.com"); cust = user(pf, "c@example.com"); c = pf._c(cust)
    pf.admin_set_pricing(admin, {"compute_usd_per_hour": 1.0, "free_compute_hours_per_month": 0, "tax_rate_percent": 20, "no_tax_with_vat_id_abroad": True})
    pf.admin_set_company(admin, {"name": "Acme", "country": "FR", "vat_id": "FR1"})
    pf.update_org(c, billing={"name": "Firma GmbH", "country": "DE", "vat_id": "DE999"})
    app = pf.create_app(c, "svc"); usage_month(pf, app, clk, 2)
    assert pf.billing(c)["estimate"]["tax_rate"] == 0.0                              # DE business with a VAT id, seller is in FR
    pf.update_org(c, billing={"name": "Firma GmbH", "country": "DE", "vat_id": ""})
    assert pf.billing(c)["estimate"]["tax_rate"] == 20                               # no VAT id: tax applies
    clk.t += 40 * 86400
    write_usage(pf.usage_path, [{"ts": clk.t, "tenant": app["tenant"], "ok": True, "wall_s": 60}])        # 1 minute: below the minimum
    clk.t += 40 * 86400
    invs = {i["period"]: i for i in pf.billing(c)["invoices"]}
    waived = [i for i in invs.values() if i["status"] == "waived"][0]
    assert waived["number"] is None
    with pytest.raises(ApiError):
        pf.invoice_pdf(c, waived["id"])


# ------------------------------------------------------------------------------------------------ mail queue
class ReuseServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class FakeSmtp(socketserver.StreamRequestHandler):
    def handle(self):
        got = self.server.received
        self.wfile.write(b"220 fake\r\n")
        data = False; body = []
        while True:
            line = self.rfile.readline()
            if not line:
                return
            if data:
                if line == b".\r\n":
                    data = False; got.append(b"".join(body).decode(errors="replace")); self.wfile.write(b"250 ok\r\n")
                else:
                    body.append(line)
                continue
            cmd = line[:4].upper()
            if cmd in (b"EHLO", b"HELO"):
                self.wfile.write(b"250 fake\r\n")
            elif cmd in (b"MAIL", b"RCPT"):
                self.wfile.write(b"250 ok\r\n")
            elif cmd == b"DATA":
                data = True; self.wfile.write(b"354 go\r\n")
            elif cmd == b"QUIT":
                self.wfile.write(b"221 bye\r\n"); return
            else:
                self.wfile.write(b"250 ok\r\n")


def test_mail_is_delivered_over_smtp_and_retried_with_backoff_when_the_server_is_down(tmp_path):
    srv = ReuseServer(("127.0.0.1", 0), FakeSmtp); srv.received = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    smtp = {"host": "127.0.0.1", "port": port, "from": "no-reply@example.com", "starttls": False}
    pf, _, clk = make(tmp_path, smtp=smtp)
    user(pf, "first@example.com")
    assert srv.received and "Subject: Welcome" in srv.received[0] or any("Confirm your e-mail" in m for m in srv.received)
    assert all(m["sent"] for m in mails(pf))
    srv.shutdown(); srv.server_close()                                                # the relay goes away
    pf.reset_request("first@example.com", "9.9.9.9")
    last = mails(pf)[-1]
    assert last["sent"] is None and last["attempts"] == 1 and last["last_error"]
    assert pf.mailer.flush() == 0                                                     # not due yet: backoff
    srv2 = ReuseServer(("127.0.0.1", port), FakeSmtp); srv2.received = []
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    try:
        clk.t += 3600
        assert pf.mailer.flush() == 1 and srv2.received and "Reset your password" in srv2.received[0]
        assert mails(pf)[-1]["sent"] is not None
        admin = pf.db.one("SELECT * FROM users WHERE is_admin=1")
        assert pf.admin_test_mail(admin, "me@example.com")["sent"] is True
    finally:
        srv2.shutdown(); srv2.server_close()


def test_test_mail_is_refused_without_smtp(tmp_path):
    pf, _, _ = make(tmp_path)
    admin = user(pf, "admin@example.com")
    with pytest.raises(ApiError) as e:
        pf.admin_test_mail(admin, "x@example.com")
    assert e.value.status == 503


# ------------------------------------------------------------------------------------------------ HTTP: org header, rate limit, pagination, 2FA flow
@pytest.fixture
def web2(tmp_path):
    pf, auth, _ = make(tmp_path)
    pf.dev_outbox = True
    srv = serve(pf, port=0); threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield Http(srv.server_address[1]), pf
    srv.shutdown(); srv.server_close()


def test_http_org_header_selects_the_workspace_and_non_members_get_404(web2):
    c, pf = web2
    st, d, _ = c.req("POST", "/api/signup", {"email": "o@example.com", "password": PW, "name": "O"}); c.csrf = d["csrf"]
    me = c.req("GET", "/api/me")[1]
    personal = me["org"]
    assert [o["role"] for o in me["orgs"]] == ["owner"]
    org = c.req("POST", "/api/orgs", {"name": "Team"})[1]["org"]
    assert c.req("POST", "/api/apps", {"name": "in-personal"})[0] == 201
    assert c.req("POST", "/api/apps", {"name": "in-team"}, headers={"X-Org": str(org["id"])})[0] == 201
    assert [a["name"] for a in c.req("GET", "/api/apps")[1]["apps"]] == ["in-personal"]
    assert [a["name"] for a in c.req("GET", "/api/apps", headers={"X-Org": str(org["id"])})[1]["apps"]] == ["in-team"]
    other = Http(c.port)
    st, d, _ = other.req("POST", "/api/signup", {"email": "x@example.com", "password": PW, "name": "X"}); other.csrf = d["csrf"]
    assert other.req("GET", "/api/apps", headers={"X-Org": str(org["id"])})[0] == 404          # not a member
    assert other.req("GET", "/api/apps", headers={"X-Org": "abc"})[0] == 400
    assert c.req("GET", "/api/org", headers={"X-Org": str(org["id"])})[1]["org"]["role"] == "owner"


def test_http_two_factor_flow_end_to_end(web2):
    c, pf = web2
    st, d, _ = c.req("POST", "/api/signup", {"email": "t@example.com", "password": PW, "name": "T"}); c.csrf = d["csrf"]
    sec_ = c.req("POST", "/api/2fa/setup")[1]["secret"]
    assert c.req("POST", "/api/2fa/enable", {"code": "000000"})[0] == 400
    codes = c.req("POST", "/api/2fa/enable", {"code": totp.code_at(sec_, int(pf.clock() // 30))})[1]["recovery_codes"]
    assert len(codes) == 8
    fresh = Http(c.port)
    st, d, _ = fresh.req("POST", "/api/login", {"email": "t@example.com", "password": PW})
    assert st == 200 and d.get("needs_2fa") and "user" not in d and fresh.cookie is None        # no session before the second factor
    assert fresh.req("GET", "/api/apps")[0] == 401
    assert fresh.req("POST", "/api/login/2fa", {"ticket": d["ticket"], "code": "123456"})[0] == 401
    st, d2, _ = fresh.req("POST", "/api/login/2fa", {"ticket": d["ticket"], "code": codes[0]})
    assert st == 200 and fresh.cookie
    fresh.csrf = d2["csrf"]
    assert fresh.req("GET", "/api/apps")[0] == 200


def test_http_pagination_and_per_token_rate_limit_and_pdf_download(web2):
    c, pf = web2
    st, d, _ = c.req("POST", "/api/signup", {"email": "p@example.com", "password": PW, "name": "P"}); c.csrf = d["csrf"]
    for i in range(5):
        c.req("POST", "/api/apps", {"name": f"a{i}"})
    page = c.req("GET", "/api/apps?limit=2&offset=1")[1]
    assert page["total"] == 5 and [a["name"] for a in page["apps"]] == ["a1", "a2"] and page["limit"] == 2 and page["offset"] == 1
    assert len(c.req("GET", "/api/apps?limit=9999")[1]["apps"]) == 5                          # capped, not an error
    tok = c.req("POST", "/api/tokens", {"name": "t", "scope": "read"})[1]["token"]["token"]
    from spatial.platform.security import RateLimiter
    pf.token_limit = RateLimiter(3, 60)
    bare = Http(c.port)
    codes = [bare.req("GET", "/api/apps", headers={"Authorization": "Bearer " + tok})[0] for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert c.req("GET", "/api/invoices/1/pdf")[0] == 404


# ------------------------------------------------------------------------------------------------ migration
def test_an_old_database_is_migrated_with_personal_organisations_and_nothing_is_lost(tmp_path):
    path = str(tmp_path / "old.db")
    c = sqlite3.connect(path)
    c.executescript("""
    CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, pw_hash TEXT NOT NULL, created REAL NOT NULL,
      is_admin INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0);
    CREATE TABLE apps(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', budget_usd REAL, created REAL NOT NULL, deleted REAL);
    CREATE TABLE invoices(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, period TEXT NOT NULL, amount_usd REAL NOT NULL, status TEXT NOT NULL,
      lines TEXT NOT NULL, created REAL NOT NULL, paid REAL, provider_ref TEXT, UNIQUE(user_id, period));
    CREATE TABLE outbox(id INTEGER PRIMARY KEY, to_addr TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL, sent REAL);
    INSERT INTO users(id,email,name,pw_hash,created,is_admin) VALUES(1,'old@example.com','Old User','x',1,1);
    INSERT INTO apps(id,user_id,name,created) VALUES(7,1,'legacy',1);
    INSERT INTO invoices(id,user_id,period,amount_usd,status,lines,created) VALUES(3,1,'2026-01',2.5,'open','[]',1);
    """)
    c.commit(); c.close()
    db = DB(path)
    u = db.one("SELECT * FROM users WHERE id=1")
    assert u["personal_org"] and db.one("SELECT role FROM members WHERE user_id=1")["role"] == "owner"
    assert db.one("SELECT org_id FROM apps WHERE id=7")["org_id"] == u["personal_org"]
    assert db.one("SELECT org_id, amount_usd FROM invoices WHERE id=3")["org_id"] == u["personal_org"]
    DB(path)                                                                          # opening again changes nothing
    assert db.one("SELECT COUNT(*) c FROM orgs")["c"] == 1
    pf = Platform(db)
    row = db.one("SELECT * FROM users WHERE id=1")
    assert [a["name"] for a in pf.list_apps(row)] == ["legacy"]

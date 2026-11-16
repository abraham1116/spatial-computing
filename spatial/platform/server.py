"""HTTP front of the account service: JSON API plus the single-page app in static/.

Safety: binds 127.0.0.1 unless --allow-remote is given; session cookie is HttpOnly + SameSite=Strict (+ Secure
with --secure-cookies, which you want behind TLS); every state-changing request needs the CSRF token header and
a same-origin Origin; strict CSP (no inline script or style); bodies are capped at 64 KiB.
"""
from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
from http import cookies
from pathlib import Path
from urllib.parse import urlparse

from ..core.auth import Authorizer, authorizer_from_file
from .billing import Pricing, Stripe
from .db import DB
from .service import ApiError, Platform

STATIC = Path(__file__).parent / "static"
MAX_BODY = 64 * 1024
COOKIE = "sp_session"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def make_handler(pf: Platform, secure_cookies: bool):
    routes: list[tuple] = []     # method, pattern, name, needs_auth, needs_csrf, cookie_only

    def route(method, pattern, name, auth=True, csrf=None, cookie_only=False):
        routes.append((method, re.compile("^" + pattern + "$"), name, auth, (method != "GET") if csrf is None else csrf, cookie_only))

    route("POST", "/api/signup", "signup", auth=False, csrf=False)
    route("POST", "/api/login", "login", auth=False, csrf=False)
    route("POST", "/api/password/reset-request", "reset_request", auth=False, csrf=False)
    route("POST", "/api/password/reset", "reset_confirm", auth=False, csrf=False)
    route("POST", "/api/billing/webhook", "webhook", auth=False, csrf=False)
    route("GET", "/api/health", "health", auth=False)
    route("GET", "/api/me", "me", auth=False)
    route("POST", "/api/logout", "logout", auth=False, csrf=False)
    route("POST", "/api/password/change", "change_password", cookie_only=True)
    route("PATCH", "/api/me", "update_me")
    route("DELETE", "/api/me", "delete_me", cookie_only=True)
    route("GET", "/api/export", "export")
    route("GET", "/api/tokens", "tokens_list")
    route("POST", "/api/tokens", "tokens_create", cookie_only=True)
    route("DELETE", r"/api/tokens/(\d+)", "tokens_revoke", cookie_only=True)
    route("GET", "/api/sessions", "sessions_list", cookie_only=True)
    route("DELETE", r"/api/sessions/([0-9a-f]{12})", "sessions_revoke", cookie_only=True)
    route("GET", "/api/activity", "activity")
    route("GET", "/api/fleet", "fleet")
    route("GET", "/api/workloads", "workloads")
    route("POST", r"/api/apps/(\d+)/jobs", "jobs_submit")
    route("GET", r"/api/apps/(\d+)/jobs/(\d+)", "jobs_status")
    route("GET", "/api/admin/overview", "admin_overview")
    route("GET", "/api/admin/users", "admin_users")
    route("GET", "/api/overview", "overview")
    route("GET", "/api/apps", "apps_list")
    route("POST", "/api/apps", "apps_create")
    route("GET", r"/api/apps/(\d+)", "apps_get")
    route("PATCH", r"/api/apps/(\d+)", "apps_update")
    route("DELETE", r"/api/apps/(\d+)", "apps_delete")
    route("POST", r"/api/apps/(\d+)/keys", "keys_create")
    route("DELETE", r"/api/apps/(\d+)/keys/(\d+)", "keys_revoke")
    route("GET", r"/api/apps/(\d+)/usage", "usage")
    route("POST", r"/api/apps/(\d+)/test-job", "test_job")
    route("GET", "/api/billing", "billing")
    route("POST", "/api/billing/pay", "pay")
    route("GET", "/api/dev/outbox", "outbox", auth=False)        # local development only: see mails without an SMTP server

    class H(http.server.BaseHTTPRequestHandler):
        server_version = "SpatialPlatform"
        sys_version = ""

        def log_message(self, *a):
            pass

        # ---------------------------------------------------------------- helpers
        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None, cache: str = "no-store"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj, extra: dict | None = None):
            self._send(status, json.dumps(obj).encode(), "application/json", extra)

        def _ip(self) -> str:
            return self.client_address[0]

        def _cookie(self) -> str | None:
            c = cookies.SimpleCookie(self.headers.get("Cookie") or "")
            return c[COOKIE].value if COOKIE in c else None

        def _set_cookie(self, token: str | None) -> dict:
            flags = "HttpOnly; SameSite=Strict; Path=/" + ("; Secure" if secure_cookies else "")
            if token is None:
                return {"Set-Cookie": f"{COOKIE}=; Max-Age=0; {flags}"}
            return {"Set-Cookie": f"{COOKIE}={token}; Max-Age=604800; {flags}"}

        def _body(self) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ApiError(413, "request too large")
            return self.rfile.read(n) if n else b""

        def _same_origin(self) -> bool:
            o = self.headers.get("Origin")
            return o is None or urlparse(o).netloc == self.headers.get("Host")

        # ---------------------------------------------------------------- dispatch
        def _handle(self, method: str):
            u = urlparse(self.path)
            path = u.path
            if method == "GET" and not path.startswith("/api/"):
                return self._static(path)
            for m, pat, name, needs_auth, needs_csrf, cookie_only in routes:
                mt = pat.match(path)
                if m != method or not mt:
                    continue
                try:
                    return getattr(self, "h_" + name)(mt.groups(), u, *self._ctx(needs_auth, needs_csrf, cookie_only, method))
                except ApiError as e:
                    return self._json(e.status, {"error": e.message})
                except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                    return self._json(400, {"error": "malformed request"})
                except Exception as e:                                   # never leak internals
                    sys.stderr.write(f"internal error on {method} {path}: {type(e).__name__}: {e}\n")
                    return self._json(500, {"error": "internal error"})
            self._json(404, {"error": "not found"})

        def _ctx(self, needs_auth: bool, needs_csrf: bool, cookie_only: bool = False, method: str = "GET"):
            authz = self.headers.get("Authorization") or ""
            if authz.startswith("Bearer "):                           # personal access token: no cookie, so no CSRF; limited by its scope
                b = pf.bearer(authz[7:].strip())
                if b is None:
                    raise ApiError(401, "invalid or expired token")
                if cookie_only:
                    raise ApiError(403, "this action needs a signed-in browser session, not a token")
                if method != "GET" and b[1] != "write":
                    raise ApiError(403, "this token is read-only")
                return (b[0], None),
            if needs_csrf and not self._same_origin():
                raise ApiError(403, "cross-origin request refused")
            s = pf.session(self._cookie())
            if needs_auth and s is None:
                raise ApiError(401, "sign in required")
            if needs_csrf and s is not None and not secrets.compare_digest(self.headers.get("X-CSRF-Token") or "", s[1]):
                raise ApiError(403, "missing or wrong CSRF token")
            return s if s else (None, None),

        def _data(self) -> dict:
            raw = self._body()
            d = json.loads(raw) if raw else {}
            if not isinstance(d, dict):
                raise ValueError("object expected")
            return d

        def do_GET(self): self._handle("GET")
        def do_POST(self): self._handle("POST")
        def do_PATCH(self): self._handle("PATCH")
        def do_DELETE(self): self._handle("DELETE")

        def _static(self, path: str):
            if path in ("/", "") or not Path(path).suffix:
                path = "/index.html"                                       # single-page app: every route serves it
            f = (STATIC / path.lstrip("/")).resolve()
            if STATIC.resolve() not in f.parents or not f.is_file():
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            self._send(200, f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""), cache="no-cache")

        # ---------------------------------------------------------------- handlers: (groups, url, session)
        def h_health(self, g, u, s):
            self._json(200, {"ok": True})

        def h_me(self, g, u, s):
            user, csrf = s
            self._json(200, {"user": pf.user_view(user) if user else None, "csrf": csrf,
                             "hub": pf.hub_public, "payments": pf.stripe.configured, "docs": pf.docs_url})

        def h_signup(self, g, u, s):
            d = self._data()
            pf.signup(d.get("email"), d.get("password"), d.get("name"), self._ip())
            token, csrf, user = pf.login(d.get("email"), d.get("password"), self._ip(), self.headers.get("User-Agent", ""))
            self._json(201, {"user": user, "csrf": csrf}, self._set_cookie(token))

        def h_login(self, g, u, s):
            d = self._data()
            token, csrf, user = pf.login(d.get("email"), d.get("password"), self._ip(), self.headers.get("User-Agent", ""))
            self._json(200, {"user": user, "csrf": csrf}, self._set_cookie(token))

        def h_logout(self, g, u, s):
            pf.logout(self._cookie())
            self._json(200, {"ok": True}, self._set_cookie(None))

        def h_reset_request(self, g, u, s):
            pf.reset_request(self._data().get("email"), self._ip())
            self._json(200, {"ok": True, "message": "If an account exists for this address, a reset link has been sent."})

        def h_reset_confirm(self, g, u, s):
            d = self._data()
            pf.reset_confirm(d.get("token"), d.get("password"))
            self._json(200, {"ok": True})

        def h_change_password(self, g, u, s):
            d = self._data()
            pf.change_password(s[0], d.get("current"), d.get("new"), self._cookie())
            self._json(200, {"ok": True})

        def h_update_me(self, g, u, s):
            self._json(200, {"user": pf.update_profile(s[0], self._data().get("name"))})

        def h_delete_me(self, g, u, s):
            pf.delete_account(s[0], self._data().get("password"))
            self._json(200, {"ok": True}, self._set_cookie(None))

        def h_export(self, g, u, s):
            self._json(200, pf.export_data(s[0]), {"Content-Disposition": 'attachment; filename="spatial-account-export.json"'})

        def h_tokens_list(self, g, u, s):
            self._json(200, {"tokens": pf.list_tokens(s[0])})

        def h_tokens_create(self, g, u, s):
            d = self._data()
            self._json(201, {"token": pf.create_token(s[0], d.get("name"), d.get("scope", "read"), d.get("ttl_days", 90))})

        def h_tokens_revoke(self, g, u, s):
            pf.revoke_token(s[0], int(g[0]))
            self._json(200, {"ok": True})

        def h_sessions_list(self, g, u, s):
            self._json(200, {"sessions": pf.list_sessions(s[0], self._cookie())})

        def h_sessions_revoke(self, g, u, s):
            pf.revoke_session(s[0], g[0])
            self._json(200, {"ok": True})

        def h_activity(self, g, u, s):
            self._json(200, {"activity": pf.activity(s[0])})

        def h_fleet(self, g, u, s):
            self._json(200, pf.fleet(s[0]))

        def h_workloads(self, g, u, s):
            self._json(200, {"workloads": pf.workloads()})

        def h_jobs_submit(self, g, u, s):
            d = self._data()
            self._json(202, pf.submit_job(s[0], int(g[0]), d.get("workload"), d.get("params") or {}))

        def h_jobs_status(self, g, u, s):
            self._json(200, pf.job_status(s[0], int(g[0]), int(g[1])))

        def h_admin_overview(self, g, u, s):
            self._json(200, pf.admin_overview(s[0]))

        def h_admin_users(self, g, u, s):
            self._json(200, {"users": pf.admin_users(s[0])})

        def h_overview(self, g, u, s):
            self._json(200, pf.overview(s[0]))

        def h_apps_list(self, g, u, s):
            self._json(200, {"apps": pf.list_apps(s[0])})

        def h_apps_create(self, g, u, s):
            d = self._data()
            self._json(201, {"app": pf.create_app(s[0], d.get("name"), d.get("description", ""), d.get("budget_usd"))})

        def h_apps_get(self, g, u, s):
            self._json(200, {"app": pf.app_view(pf._app(s[0], int(g[0])))})

        def h_apps_update(self, g, u, s):
            d = self._data()
            self._json(200, {"app": pf.update_app(s[0], int(g[0]), d.get("name"), d.get("description"), d.get("budget_usd", "keep"))})

        def h_apps_delete(self, g, u, s):
            pf.delete_app(s[0], int(g[0]))
            self._json(200, {"ok": True})

        def h_keys_create(self, g, u, s):
            d = self._data()
            self._json(201, {"key": pf.create_key(s[0], int(g[0]), d.get("name"), d.get("kind", "client"), d.get("ttl_days", 90))})

        def h_keys_revoke(self, g, u, s):
            pf.revoke_key(s[0], int(g[0]), int(g[1]))
            self._json(200, {"ok": True})

        def h_usage(self, g, u, s):
            days = int((re.search(r"days=(\d+)", u.query) or [0, 30])[1])
            self._json(200, pf.usage_for_app(s[0], int(g[0]), days))

        def h_test_job(self, g, u, s):
            self._json(200, pf.run_test_job(s[0], int(g[0])))

        def h_billing(self, g, u, s):
            self._json(200, pf.billing(s[0]))

        def h_pay(self, g, u, s):
            self._json(200, pf.pay(s[0], int(self._data().get("invoice_id"))))

        def h_webhook(self, g, u, s):
            ok = pf.webhook(self._body(), self.headers.get("Stripe-Signature", ""))
            self._json(200, {"received": True, "applied": ok})

        def h_outbox(self, g, u, s):
            if not getattr(pf, "dev_outbox", False):
                raise ApiError(404, "not found")
            rows = pf.db.q("SELECT to_addr, subject, body, created FROM outbox ORDER BY id DESC LIMIT 20")
            self._json(200, {"outbox": [dict(r) for r in rows]})

    return H


def serve(pf: Platform, host: str = "127.0.0.1", port: int = 8090, allow_remote: bool = False, secure_cookies: bool = False):
    if host not in ("127.0.0.1", "localhost", "::1") and not allow_remote:
        raise PermissionError("refusing to bind a non-loopback address without allow_remote=True (put TLS in front of it first)")

    class S(http.server.ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 256
    srv = S((host, port), make_handler(pf, secure_cookies))
    return srv


def main(argv=None):
    ap = argparse.ArgumentParser(prog="spatial platform serve")
    ap.add_argument("--db", default=str(Path.home() / ".spatial" / "platform.db"))
    ap.add_argument("--master-key-file", help="the hub's master key: lets the service issue API keys (hub credentials)")
    ap.add_argument("--hub", help="host:port the service uses to run test jobs")
    ap.add_argument("--hub-public", help="host:port shown to users as the hub address (default: --hub)")
    ap.add_argument("--usage-file", help="the hub's --usage-file, read for metering")
    ap.add_argument("--revoked-file", help="the hub's --revoked-file, written when a key is revoked")
    ap.add_argument("--pricing-file", help="JSON price list (see spatial/platform/billing.py)")
    ap.add_argument("--public-url", default=None)
    ap.add_argument("--docs-url", default="https://spatial-computing-ecru.vercel.app/docs/index.html", help="where the console's Docs link points")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--allow-remote", action="store_true")
    ap.add_argument("--secure-cookies", action="store_true", help="mark the session cookie Secure (use behind TLS)")
    ap.add_argument("--dev-outbox", action="store_true", help="expose /api/dev/outbox (reset links) for local development")
    a = ap.parse_args(argv)
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    auth = authorizer_from_file(a.master_key_file, revoked_file=a.revoked_file) if a.master_key_file else None
    smtp = None
    if os.environ.get("SMTP_HOST"):
        smtp = {"host": os.environ["SMTP_HOST"], "port": int(os.environ.get("SMTP_PORT", "587")), "user": os.environ.get("SMTP_USER"),
                "password": os.environ.get("SMTP_PASSWORD"), "from": os.environ.get("SMTP_FROM", "no-reply@localhost")}
    pf = Platform(DB(a.db), auth, a.hub, a.hub_public, a.usage_file, a.revoked_file, Pricing.load(a.pricing_file),
                  Stripe(os.environ.get("STRIPE_SECRET_KEY"), os.environ.get("STRIPE_WEBHOOK_SECRET")),
                  a.public_url or f"http://{a.host}:{a.port}", smtp=smtp, docs_url=a.docs_url)
    pf.dev_outbox = a.dev_outbox
    srv = serve(pf, a.host, a.port, a.allow_remote, a.secure_cookies)

    def ingest_loop():
        while True:
            try:
                pf.ingest_usage()
            except Exception as e:
                sys.stderr.write(f"usage ingest failed: {type(e).__name__}: {e}\n")
            time.sleep(10)
    threading.Thread(target=ingest_loop, daemon=True).start()
    print(f"platform on http://{a.host}:{srv.server_address[1]}/ (payments: {'Stripe' if pf.stripe.configured else 'not configured'}; "
          f"hub keys: {'yes' if auth else 'no'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

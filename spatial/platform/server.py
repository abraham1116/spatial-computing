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
import urllib.parse
from urllib.parse import parse_qs, urlparse

from ..core.auth import Authorizer, authorizer_from_file
from .billing import Pricing, Stripe
from .db import DB
from .service import ApiError, Platform, TwoFactorRequired

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
    route("GET", "/api/admin/settings", "admin_settings")
    route("PUT", "/api/admin/pricing", "admin_pricing")
    route("PUT", "/api/admin/company", "admin_company")
    route("POST", "/api/admin/test-mail", "admin_test_mail")
    route("GET", "/api/admin/invoices", "admin_invoices")
    route("POST", r"/api/admin/invoices/(\d+)/credit", "admin_credit")
    route("GET", r"/api/credit-notes/(\d+)/pdf", "credit_pdf")
    route("GET", r"/api/invoices/(\d+)/ubl", "invoice_ubl")
    route("GET", r"/api/credit-notes/(\d+)/ubl", "credit_ubl")
    route("GET", "/api/admin/mail", "admin_mail")
    route("POST", "/api/login/2fa", "login_2fa", auth=False, csrf=False)
    route("GET", "/api/sso/config", "sso_config", auth=False)
    route("GET", "/api/sso/start", "sso_start", auth=False)
    route("GET", "/api/sso/callback", "sso_callback", auth=False)
    route("POST", "/api/2fa/setup", "totp_setup", cookie_only=True)
    route("POST", "/api/2fa/enable", "totp_enable", cookie_only=True)
    route("POST", "/api/2fa/disable", "totp_disable", cookie_only=True)
    route("POST", "/api/verify", "verify", auth=False, csrf=False)
    route("POST", "/api/verify/resend", "verify_resend")
    route("GET", "/api/orgs", "orgs_list")
    route("POST", "/api/orgs", "orgs_create", cookie_only=True)
    route("GET", "/api/org", "org_get")
    route("PATCH", "/api/org", "org_update")
    route("DELETE", "/api/org", "org_delete", cookie_only=True)
    route("POST", "/api/org/roles", "roles_create")
    route("DELETE", r"/api/org/roles/([a-z][a-z0-9-]{0,29})", "roles_delete")
    route("POST", "/api/org/invites", "invites_create")
    route("DELETE", r"/api/org/invites/(\d+)", "invites_revoke")
    route("PATCH", r"/api/org/members/(\d+)", "members_role")
    route("DELETE", r"/api/org/members/(\d+)", "members_remove")
    route("POST", "/api/invites/accept", "invites_accept", cookie_only=True)
    route("GET", r"/api/invoices/(\d+)/pdf", "invoice_pdf")
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
                if not pf.token_limit.allow(authz[7:].strip()):
                    raise ApiError(429, "rate limit: 120 requests per minute per token")
                return (self._org(b[0]), None),
            if needs_csrf and not self._same_origin():
                raise ApiError(403, "cross-origin request refused")
            s = pf.session(self._cookie())
            if needs_auth and s is None:
                raise ApiError(401, "sign in required")
            if needs_csrf and s is not None and not secrets.compare_digest(self.headers.get("X-CSRF-Token") or "", s[1]):
                raise ApiError(403, "missing or wrong CSRF token")
            if s is not None and not pf.user_limit.allow(f"u{s[0]['id']}"):
                raise ApiError(429, "rate limit: 600 requests per minute")
            return ((self._org(s[0]), s[1]) if s else (None, None)),

        def _org(self, user):
            """The organisation the request acts in: header X-Org, else the user's personal workspace."""
            o = self.headers.get("X-Org") or (parse_qs(urlparse(self.path).query).get("org") or [None])[0]      # ?org= lets a plain link (PDF) pick the organisation
            try:
                return pf._c(user, int(o) if o else None)
            except ValueError:
                raise ApiError(400, "bad X-Org header")

        def _data(self) -> dict:
            raw = self._body()
            d = json.loads(raw) if raw else {}
            if not isinstance(d, dict):
                raise ValueError("object expected")
            return d

        def _page(self, u, items: list, key: str) -> dict:
            q = parse_qs(u.query)
            lim = max(1, min(int((q.get("limit") or [100])[0]), 500))
            off = max(0, int((q.get("offset") or [0])[0]))
            return {key: items[off:off + lim], "total": len(items), "limit": lim, "offset": off}

        def do_PUT(self): self._handle("PUT")
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
            out = {"user": pf.user_view(user) if user else None, "csrf": csrf, "hub": pf.hub_public, "payments": pf.stripe.configured, "docs": pf.docs_url}
            if user:
                out.update(orgs=pf.list_orgs(user), org=user.org_id, role=user["role"], perms=sorted(user["perms"]), require_verified=pf.require_verified)
            self._json(200, out)

        def h_signup(self, g, u, s):
            d = self._data()
            pf.signup(d.get("email"), d.get("password"), d.get("name"), self._ip())
            token, csrf, user = pf.login(d.get("email"), d.get("password"), self._ip(), self.headers.get("User-Agent", ""))
            self._json(201, {"user": user, "csrf": csrf}, self._set_cookie(token))

        def h_login(self, g, u, s):
            d = self._data()
            try:
                token, csrf, user = pf.login(d.get("email"), d.get("password"), self._ip(), self.headers.get("User-Agent", ""))
            except TwoFactorRequired as e:
                return self._json(200, {"needs_2fa": True, "ticket": e.ticket})
            self._json(200, {"user": user, "csrf": csrf}, self._set_cookie(token))

        def h_sso_config(self, g, u, s):
            self._json(200, pf.sso_config())

        def _redirect(self, location: str, extra: dict | None = None):
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def h_sso_start(self, g, u, s):
            self._redirect(pf.sso_start(self._ip()))

        def h_sso_callback(self, g, u, s):
            q = parse_qs(u.query)
            try:
                if q.get("error"):
                    raise ApiError(401, "single sign-on was cancelled or refused by the provider")
                token, csrf, user = pf.sso_callback((q.get("code") or [""])[0], (q.get("state") or [""])[0], self._ip(), self.headers.get("User-Agent", ""))
            except TwoFactorRequired as e:
                return self._redirect("/#/2fa/" + e.ticket)
            except ApiError as e:
                return self._redirect("/#/login?sso_error=" + urllib.parse.quote(e.message))
            self._redirect("/#/", self._set_cookie(token))

        def h_login_2fa(self, g, u, s):
            d = self._data()
            token, csrf, user = pf.login_2fa(d.get("ticket"), d.get("code"), self._ip(), self.headers.get("User-Agent", ""))
            self._json(200, {"user": user, "csrf": csrf}, self._set_cookie(token))

        def h_totp_setup(self, g, u, s):
            self._json(200, pf.totp_setup(s[0]))

        def h_totp_enable(self, g, u, s):
            self._json(200, pf.totp_enable(s[0], self._data().get("code")))

        def h_totp_disable(self, g, u, s):
            d = self._data()
            pf.totp_disable(s[0], d.get("password"), d.get("code"))
            self._json(200, {"ok": True}, self._set_cookie(None))

        def h_verify(self, g, u, s):
            self._json(200, {"user": pf.verify_email(self._data().get("token"))})

        def h_verify_resend(self, g, u, s):
            pf.resend_verification(s[0])
            self._json(200, {"ok": True})

        def h_orgs_list(self, g, u, s):
            self._json(200, {"orgs": pf.list_orgs(s[0])})

        def h_orgs_create(self, g, u, s):
            self._json(201, {"org": pf.create_org(s[0], self._data().get("name"))})

        def h_org_get(self, g, u, s):
            self._json(200, {"org": pf.org_detail(s[0])})

        def h_org_update(self, g, u, s):
            d = self._data()
            self._json(200, {"org": pf.update_org(s[0], d.get("name"), d.get("billing"))})

        def h_org_delete(self, g, u, s):
            pf.delete_org(s[0])
            self._json(200, {"ok": True})

        def h_roles_create(self, g, u, s):
            d = self._data()
            self._json(201, {"role": pf.create_role(s[0], d.get("name"), d.get("perms"))})

        def h_roles_delete(self, g, u, s):
            pf.delete_role(s[0], g[0])
            self._json(200, {"ok": True})

        def h_invites_create(self, g, u, s):
            d = self._data()
            self._json(201, {"invite": pf.invite(s[0], d.get("email"), d.get("role", "member"), d.get("apps"))})

        def h_invites_revoke(self, g, u, s):
            pf.revoke_invite(s[0], int(g[0]))
            self._json(200, {"ok": True})

        def h_invites_accept(self, g, u, s):
            self._json(200, {"org": pf.accept_invite(s[0], self._data().get("token"))})

        def h_members_role(self, g, u, s):
            d = self._data()
            if "role" in d:
                pf.set_member_role(s[0], int(g[0]), d["role"])
            if "apps" in d:
                pf.set_member_apps(s[0], int(g[0]), d["apps"])
            self._json(200, {"ok": True})

        def h_members_remove(self, g, u, s):
            pf.remove_member(s[0], int(g[0]))
            self._json(200, {"ok": True})

        def h_invoice_pdf(self, g, u, s):
            pdf, name = pf.invoice_pdf(s[0], int(g[0]))
            self._send(200, pdf, "application/pdf", {"Content-Disposition": f'attachment; filename="{name}"'})

        def h_admin_settings(self, g, u, s):
            self._json(200, pf.admin_settings(s[0]))

        def h_admin_pricing(self, g, u, s):
            self._json(200, pf.admin_set_pricing(s[0], self._data()))

        def h_admin_company(self, g, u, s):
            self._json(200, pf.admin_set_company(s[0], self._data()))

        def h_admin_test_mail(self, g, u, s):
            self._json(200, pf.admin_test_mail(s[0], self._data().get("to")))

        def h_admin_invoices(self, g, u, s):
            self._json(200, self._page(u, pf.admin_invoices(s[0], 500), "invoices"))

        def h_admin_credit(self, g, u, s):
            d = self._data()
            self._json(201, {"credit_note": pf.admin_credit_note(s[0], int(g[0]), d.get("amount_usd"), d.get("reason"))})

        def h_invoice_ubl(self, g, u, s):
            xml, name = pf.invoice_ubl(s[0], int(g[0]))
            self._send(200, xml, "application/xml; charset=utf-8", {"Content-Disposition": f'attachment; filename="{name}"'})

        def h_credit_ubl(self, g, u, s):
            xml, name = pf.credit_note_ubl(s[0], int(g[0]))
            self._send(200, xml, "application/xml; charset=utf-8", {"Content-Disposition": f'attachment; filename="{name}"'})

        def h_credit_pdf(self, g, u, s):
            pdf, name = pf.credit_note_pdf(s[0], int(g[0]))
            self._send(200, pdf, "application/pdf", {"Content-Disposition": f'attachment; filename="{name}"'})

        def h_admin_mail(self, g, u, s):
            self._json(200, {"mail": pf.admin_mail(s[0])})

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
            self._json(200, self._page(u, pf.list_tokens(s[0]), "tokens"))

        def h_tokens_create(self, g, u, s):
            d = self._data()
            self._json(201, {"token": pf.create_token(s[0], d.get("name"), d.get("scope", "read"), d.get("ttl_days", 90))})

        def h_tokens_revoke(self, g, u, s):
            pf.revoke_token(s[0], int(g[0]))
            self._json(200, {"ok": True})

        def h_sessions_list(self, g, u, s):
            self._json(200, self._page(u, pf.list_sessions(s[0], self._cookie()), "sessions"))

        def h_sessions_revoke(self, g, u, s):
            pf.revoke_session(s[0], g[0])
            self._json(200, {"ok": True})

        def h_activity(self, g, u, s):
            self._json(200, self._page(u, pf.activity(s[0], 200), "activity"))

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
            self._json(200, self._page(u, pf.admin_users(s[0]), "users"))

        def h_overview(self, g, u, s):
            self._json(200, pf.overview(s[0]))

        def h_apps_list(self, g, u, s):
            self._json(200, self._page(u, pf.list_apps(s[0]), "apps"))

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
    ap.add_argument("--smtp-host", help="SMTP server for outgoing e-mail (password in the SMTP_PASSWORD environment variable)")
    ap.add_argument("--smtp-port", type=int, default=587)
    ap.add_argument("--smtp-user")
    ap.add_argument("--smtp-from", default="no-reply@localhost")
    ap.add_argument("--smtp-ssl", action="store_true", help="implicit TLS (port 465) instead of STARTTLS")
    ap.add_argument("--smtp-ca-file", help="CA certificate (PEM) that signed the SMTP server's certificate, for a private relay; certificates are always verified")
    ap.add_argument("--smtp-no-starttls", action="store_true", help="plain SMTP, for a local relay only")
    ap.add_argument("--oidc-issuer", help="OpenID Connect provider URL (enables 'Sign in with ...'); the client secret goes in OIDC_CLIENT_SECRET")
    ap.add_argument("--oidc-client-id")
    ap.add_argument("--oidc-name", default="Single sign-on", help="label of the sign-in button")
    ap.add_argument("--oidc-domains", default="", help="comma list: only these e-mail domains may sign in this way")
    ap.add_argument("--oidc-no-create", action="store_true", help="only existing accounts may sign in this way")
    ap.add_argument("--require-verified", choices=["auto", "yes", "no"], default="auto", help="e-mail verification before keys and jobs (auto: only when SMTP is configured)")
    ap.add_argument("--embedded-hub", action="store_true", help="run the fleet hub inside this process (one container, one command): needs --master-key-file")
    ap.add_argument("--hub-listen", default="127.0.0.1:7700", help="with --embedded-hub: host:port the hub listens on (use 0.0.0.0:7700 for a container; remote binding is allowed only with --allow-remote)")
    ap.add_argument("--dev-outbox", action="store_true", help="expose /api/dev/outbox (reset links) for local development")
    a = ap.parse_args(argv)
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    if not a.master_key_file and os.environ.get("HUB_MASTER_KEY"):                      # hosts that give secrets as environment variables only
        kf = Path(a.db).with_name("master.key")
        fd = os.open(kf, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(os.environ["HUB_MASTER_KEY"])
        a.master_key_file = str(kf)
    embedded = None
    if a.embedded_hub:
        if not a.master_key_file:
            raise SystemExit("--embedded-hub needs --master-key-file (the hub authenticates every call with credentials this service issues)")
        if a.hub:
            raise SystemExit("--embedded-hub and --hub are exclusive")
        from ..fleet.hub import serve_hub
        hh, _, hp = a.hub_listen.rpartition(":")
        a.usage_file = a.usage_file or str(Path(a.db).with_name("hub-usage.jsonl"))
        a.revoked_file = a.revoked_file or str(Path(a.db).with_name("hub-revoked.txt"))
        hub_auth = authorizer_from_file(a.master_key_file, revoked_file=a.revoked_file)
        hsrv, hub = serve_hub(None, hh or "127.0.0.1", int(hp), a.allow_remote, hub_auth)
        hub.usage_path = a.usage_file
        hsrv.start()
        a.hub = f"127.0.0.1:{hsrv.port}"
        a.hub_public = a.hub_public or f"{hh or '127.0.0.1'}:{hsrv.port}"
        embedded = hsrv
    auth = authorizer_from_file(a.master_key_file, revoked_file=a.revoked_file) if a.master_key_file else None
    smtp = None
    host = a.smtp_host or os.environ.get("SMTP_HOST")
    if host:
        smtp = {"host": host, "port": a.smtp_port if a.smtp_host else int(os.environ.get("SMTP_PORT", "587")), "user": a.smtp_user or os.environ.get("SMTP_USER"),
                "password": os.environ.get("SMTP_PASSWORD"), "from": a.smtp_from if a.smtp_host else os.environ.get("SMTP_FROM", "no-reply@localhost"),
                "ssl": a.smtp_ssl, "starttls": not a.smtp_no_starttls, "ca_file": a.smtp_ca_file or os.environ.get("SMTP_CA_FILE")}
    pf = Platform(DB(a.db), auth, a.hub, a.hub_public, a.usage_file, a.revoked_file, Pricing.load(a.pricing_file),
                  Stripe(os.environ.get("STRIPE_SECRET_KEY"), os.environ.get("STRIPE_WEBHOOK_SECRET")),
                  a.public_url or f"http://{a.host}:{a.port}", smtp=smtp, docs_url=a.docs_url,
                  require_verified={"auto": None, "yes": True, "no": False}[a.require_verified])
    pf.dev_outbox = a.dev_outbox
    if a.oidc_issuer:
        from .oidc import Oidc
        secret = os.environ.get("OIDC_CLIENT_SECRET", "")
        if not (a.oidc_client_id and secret):
            raise SystemExit("--oidc-issuer needs --oidc-client-id and the OIDC_CLIENT_SECRET environment variable")
        pf.oidc = Oidc(a.oidc_issuer, a.oidc_client_id, secret, f"{pf.public_url}/api/sso/callback", a.oidc_name,
                       tuple(d.strip().lower() for d in a.oidc_domains.split(",") if d.strip()), not a.oidc_no_create)
    srv = serve(pf, a.host, a.port, a.allow_remote, a.secure_cookies)

    def ingest_loop():
        while True:
            try:
                pf.ingest_usage()
                pf.mailer.flush()
            except Exception as e:
                sys.stderr.write(f"background task failed: {type(e).__name__}: {e}\n")
            time.sleep(10)
    threading.Thread(target=ingest_loop, daemon=True).start()
    print(f"platform on http://{a.host}:{srv.server_address[1]}/ (payments: {'Stripe' if pf.stripe.configured else 'not configured'}; "
          f"hub keys: {'yes' if auth else 'no'}" + (f"; embedded hub on {a.hub_public}" if embedded else "") + ")", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

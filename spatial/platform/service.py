"""Business logic of the account service. No HTTP here: server.py maps requests to these methods."""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from datetime import datetime, timezone

from ..core.auth import Authorizer
from . import security as sec
from . import totp as totp_mod
from . import vat as vat_mod
from .oidc import Oidc, OidcError, pkce_pair
from . import invoice_rules as rules
from . import ubl as ubl_mod
from .billing import DEFAULT_PRICING, PaymentError, Pricing, Stripe, validate_pricing
from .db import DB
from .mailer import Mailer
from .pdf import invoice_pdf as render_invoice

SESSION_TTL_S = 7 * 24 * 3600
MAX_APPS = 20
MAX_KEYS_PER_APP = 10
KEY_KINDS = {"client": ["fleet:submit", "fleet:read"], "node": ["fleet:report", "fleet:work"]}


# name -> title, one-line description, {parameter: (suggested default, minimum, maximum)}
CATALOG = {
    "montecarlo_pi": dict(title="Monte Carlo pi", doc="Estimate pi by random sampling (CPU-bound, embarrassingly parallel).", params={"samples": (1_000_000, 1000, 50_000_000)}),
    "mandel_numba_parallel": dict(title="Mandelbrot (multi-core)", doc="Iteration counts of the Mandelbrot set on a grid, Numba on all cores.", params={"n": (600, 16, 3000), "iters": (200, 10, 2000)}),
    "pk_mandel_cpu": dict(title="Portable kernel: Mandelbrot", doc="The same kernel source that also runs on a Metal GPU, on the CPU.", params={"n": (512, 16, 2048), "iters": (200, 10, 2000)}),
    "pk_batch_score_cpu": dict(title="Portable kernel: batch scoring", doc="Fraud/risk/ranking/anomaly-shaped batch scoring (synthetic signals, no real model) on the CPU.", params={"n": (512, 16, 2048), "signals": (16, 1, 200)}),
    "matmul": dict(title="Matrix multiply", doc="Dense float64 matrix product of size n.", params={"n": (600, 16, 1500)}),
    "heat_numba": dict(title="Heat diffusion", doc="2-D heat diffusion from a hot square (simulation engine, Numba).", params={"n": (200, 16, 800), "steps": (500, 1, 5000)}),
    "nbody": dict(title="N-body", doc="Leapfrog N-body integration; returns the relative energy drift.", params={"bodies": (100, 2, 300), "steps": (400, 1, 2000)}),
    "option_mc": dict(title="Option pricing (Monte Carlo)", doc="European call price by Monte Carlo (scientific engine).", params={"paths": (1_000_000, 1000, 5_000_000)}),
    "harmonic_rk4": dict(title="Harmonic oscillator (RK4)", doc="Runge-Kutta solution of x'' = -omega^2 x, compared with the exact answer.", params={"omega": (1.0, 0.01, 100.0), "t_end": (6.0, 0.1, 1000.0), "steps": (2000, 10, 1_000_000)}),
    "hologram_peak": dict(title="Hologram synthesis", doc="Synthesise a one-point hologram and reconstruct it (holographic engine).", params={"n": (256, 32, 1024)}),
    "sha256_chain": dict(title="SHA-256 chain", doc="Hash-bound workload: memory bandwidth and SHA throughput.", params={"rounds": (200, 1, 2000)}),
}


ROLES = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}          # the built-in roles, lowest to highest
# Every signed-in member can READ their organization's apps, usage, fleet and jobs. Everything else is a permission:
PERMS = {
    "apps.write": "create and rename apps",
    "apps.delete": "delete apps",
    "apps.budget": "set app budgets",
    "keys.write": "create and revoke API keys",
    "jobs.submit": "submit jobs",
    "billing.read": "see usage charges, invoices and credit notes",
    "billing.pay": "pay invoices",
    "org.manage": "rename the organization and edit billing details",
    "members.manage": "invite and remove members, change roles, define roles",
    "org.delete": "delete the organization",
    "members.owner": "appoint and remove owners",
}
BUILTIN = {
    "viewer": frozenset(),
    "member": frozenset({"apps.write", "keys.write", "jobs.submit"}),
    "admin": frozenset({"apps.write", "apps.delete", "apps.budget", "keys.write", "jobs.submit", "billing.read", "billing.pay", "org.manage", "members.manage"}),
    "owner": frozenset(PERMS),
}


class Ctx(dict):
    """A signed-in user acting inside one organisation: the user's columns plus org_id and role."""
    @property
    def org_id(self) -> int:
        return self["org_id"]


class TwoFactorRequired(Exception):
    def __init__(self, ticket: str):
        super().__init__("two-factor code required")
        self.ticket = ticket


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def period_of(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m")


def period_bounds(period: str) -> tuple[float, float]:
    y, m = int(period[:4]), int(period[5:7])
    a = datetime(y, m, 1, tzinfo=timezone.utc)
    b = datetime(y + (m == 12), 1 if m == 12 else m + 1, 1, tzinfo=timezone.utc)
    return a.timestamp(), b.timestamp()


class Platform:
    def __init__(self, db: DB, authorizer: Authorizer | None = None, hub_addr: str | None = None, hub_public_addr: str | None = None,
                 usage_path: str | None = None, revoked_path: str | None = None, pricing: Pricing | None = None,
                 stripe: Stripe | None = None, public_url: str = "http://127.0.0.1:8090", clock=time.time, smtp: dict | None = None,
                 docs_url: str = "https://spatial-computing-ecru.vercel.app/docs/index.html", require_verified: bool | None = None):
        self.docs_url = docs_url
        self.db, self.auth, self.hub_addr, self.hub_public = db, authorizer, hub_addr, hub_public_addr or hub_addr
        self.usage_path, self.revoked_path = usage_path, revoked_path
        self._pricing0 = pricing or Pricing()
        self.stripe, self.public_url, self.clock, self.smtp = stripe or Stripe(None, None), public_url, clock, smtp
        self.mailer = Mailer(db, smtp, clock)
        # e-mail verification is enforced only when mail can really be delivered (otherwise nobody could ever verify)
        self.require_verified = bool(smtp) if require_verified is None else require_verified
        self.signup_limit = sec.RateLimiter(10, 3600, clock)
        self.login_limit = sec.RateLimiter(20, 600, clock)
        self.reset_limit = sec.RateLimiter(5, 3600, clock)
        self.oidc: Oidc | None = None
        self.vies_base = vat_mod.VIES
        self.token_limit = sec.RateLimiter(120, 60, clock)       # per personal access token
        self.user_limit = sec.RateLimiter(600, 60, clock)        # per signed-in user

    # ------------------------------------------------------------------ settings stored by the operator (pricing, company)
    def _setting(self, key: str):
        r = self.db.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(r["value"]) if r else None

    def _set_setting(self, key: str, value) -> None:
        self.db.x("INSERT INTO settings(key,value,updated) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
                  (key, json.dumps(value), self.clock()))

    @property
    def pricing(self) -> Pricing:
        d = self._setting("pricing")
        return Pricing(validate_pricing(d)) if d else self._pricing0

    @property
    def pricing_is_default(self) -> bool:
        return self._setting("pricing") is None and self._pricing0.data == DEFAULT_PRICING

    def company(self) -> dict:
        return {"name": "", "address": "", "city": "", "postal_code": "", "vat_id": "", "country": "", "email": "", "registration_no": "", "legal_form": "",
                "share_capital": "", "tax_no": "", "iban": "", "bic": "", "payment_terms_days": 30, "legal_footer": "", "tax_exempt_note": "", **(self._setting("company") or {})}

    # ------------------------------------------------------------------ context: who acts, in which organisation, with which role
    def _c(self, user, org_id: int | None = None) -> Ctx:
        if isinstance(user, Ctx) and (org_id is None or org_id == user["org_id"]):
            return user
        base = dict(user)
        oid = org_id or base.get("personal_org")
        m = self.db.one("SELECT role, app_ids FROM members WHERE org_id=? AND user_id=?", (oid, base["id"]))
        if not m:
            raise ApiError(404, "organization not found")
        base["org_id"], base["role"] = oid, m["role"]
        base["app_scope"] = None if m["app_ids"] is None else frozenset(json.loads(m["app_ids"]))          # None = every app of the organization
        base["perms"] = self._role_perms(oid, m["role"])
        return Ctx(base)

    def _role_perms(self, org_id: int, role: str) -> frozenset:
        if role in BUILTIN:
            return BUILTIN[role]
        r = self.db.one("SELECT perms FROM org_roles WHERE org_id=? AND name=?", (org_id, role))
        return frozenset(json.loads(r["perms"])) if r else frozenset()

    @staticmethod
    def _has(c: Ctx, perm: str) -> bool:
        return perm in c["perms"]

    def _need(self, c: Ctx, perm: str) -> None:
        if perm not in c["perms"]:
            raise ApiError(403, f"your role ({c['role']}) cannot {PERMS.get(perm, perm)}")

    def _may_grant(self, c: Ctx, role: str) -> None:
        """Nobody can hand out more than they hold: a role can be given only if all its permissions are the giver's own."""
        if role in BUILTIN:
            perms = BUILTIN[role]
        else:
            r = self.db.one("SELECT perms FROM org_roles WHERE org_id=? AND name=?", (c.org_id, role))
            if not r:
                raise ApiError(400, "unknown role")
            perms = frozenset(json.loads(r["perms"]))
        if not perms <= c["perms"]:
            raise ApiError(403, "you cannot give a role with permissions you do not have yourself")

    def _need_verified(self, c) -> None:
        if self.require_verified and not c["email_verified"] and not c["is_admin"]:
            raise ApiError(403, "verify your e-mail address first: open the link we sent you")

    @staticmethod
    def user_view(u) -> dict:
        return {"id": u["id"], "email": u["email"], "name": u["name"], "is_admin": bool(u["is_admin"]), "created": u["created"],
                "email_verified": bool(u["email_verified"]), "totp_enabled": bool(u["totp_enabled"])}

    def signup(self, email: str, password: str, name: str, ip: str = "") -> dict:
        email, name = (email or "").strip().lower(), (name or "").strip()
        if not self.signup_limit.allow(ip or "?"):
            raise ApiError(429, "too many sign-ups from this address; try later")
        if not sec.valid_email(email):
            raise ApiError(400, "enter a valid e-mail address")
        if not 1 <= len(name) <= 80:
            raise ApiError(400, "enter your name (up to 80 characters)")
        bad = sec.check_password_policy(password or "", email)
        if bad:
            raise ApiError(400, bad)
        first = self.db.one("SELECT COUNT(*) c FROM users")["c"] == 0
        now = self.clock()
        try:
            uid = self.db.x("INSERT INTO users(email,name,pw_hash,created,is_admin) VALUES(?,?,?,?,?)",
                            (email, name, sec.hash_password(password), now, 1 if first else 0))
        except Exception:
            raise ApiError(409, "an account with this e-mail already exists")
        oid = self.db.x("INSERT INTO orgs(name,created,personal) VALUES(?,?,1)", (f"{name}'s workspace", now))
        self.db.x("INSERT INTO members(org_id,user_id,role,created) VALUES(?,?,?,?)", (oid, uid, "owner", now))
        self.db.x("UPDATE users SET personal_org=? WHERE id=?", (oid, uid))
        self.db.event(uid, "signup")
        self._send_verification(uid, email, name)
        return self.user_view(self.db.one("SELECT * FROM users WHERE id=?", (uid,)))

    # ------------------------------------------------------------------ single sign-on (OpenID Connect)
    def sso_config(self) -> dict:
        return {"enabled": self.oidc is not None, "name": self.oidc.name if self.oidc else ""}

    def sso_start(self, ip: str = "") -> str:
        if not self.oidc:
            raise ApiError(404, "single sign-on is not configured")
        if not self.login_limit.allow(f"sso|{ip}"):
            raise ApiError(429, "too many attempts; try again in a few minutes")
        state, nonce = sec.new_token(), sec.new_token()
        verifier, challenge = pkce_pair()
        self.db.x("DELETE FROM sso_states WHERE expires<?", (self.clock(),))
        self.db.x("INSERT INTO sso_states(state_hash,nonce,verifier,expires,ip) VALUES(?,?,?,?,?)", (sec.token_hash(state), nonce, verifier, self.clock() + 600, ip))
        try:
            return self.oidc.authorize_url(state, nonce, challenge)
        except Exception as e:
            raise ApiError(502, f"the identity provider is unreachable ({type(e).__name__})")

    def sso_callback(self, code: str, state: str, ip: str = "", ua: str = "") -> tuple[str, str, dict]:
        """Returns a session like login(); raises TwoFactorRequired if the account has two-factor sign-in on (our own second factor still applies)."""
        if not self.oidc:
            raise ApiError(404, "single sign-on is not configured")
        row = self.db.one("SELECT * FROM sso_states WHERE state_hash=?", (sec.token_hash(state or ""),))
        if not row or row["expires"] < self.clock():
            raise ApiError(400, "this sign-in attempt is unknown or expired: start again")
        self.db.x("DELETE FROM sso_states WHERE state_hash=?", (row["state_hash"],))              # single use
        try:
            claims = self.oidc.verify(self.oidc.exchange(code or "", row["verifier"]), row["nonce"], self.clock())
        except OidcError as e:
            raise ApiError(401, f"single sign-on failed: {e}")
        except Exception as e:
            raise ApiError(502, f"the identity provider is unreachable ({type(e).__name__})")
        u = self.db.one("SELECT * FROM users WHERE email=?", (claims["email"],))
        if u is None:
            if not self.oidc.auto_create:
                raise ApiError(403, "no account exists for this address and automatic creation is off")
            first = self.db.one("SELECT COUNT(*) c FROM users")["c"] == 0
            now = self.clock()
            uid = self.db.x("INSERT INTO users(email,name,pw_hash,created,is_admin,email_verified) VALUES(?,?,?,?,?,1)",
                            (claims["email"], claims["name"], sec.hash_password(secrets.token_urlsafe(32)), now, 1 if first else 0))      # no usable password
            oid = self.db.x("INSERT INTO orgs(name,created,personal) VALUES(?,?,1)", (f"{claims['name']}'s workspace", now))
            self.db.x("INSERT INTO members(org_id,user_id,role,created) VALUES(?,?,?,?)", (oid, uid, "owner", now))
            self.db.x("UPDATE users SET personal_org=? WHERE id=?", (oid, uid))
            self.db.event(uid, "signup_sso")
            u = self.db.one("SELECT * FROM users WHERE id=?", (uid,))
        elif not u["email_verified"]:
            self.db.x("UPDATE users SET email_verified=1 WHERE id=?", (u["id"],))                  # the provider just confirmed the address
            u = self.db.one("SELECT * FROM users WHERE id=?", (u["id"],))
        if u["locked_until"] > self.clock():
            raise ApiError(429, "account temporarily locked; try again later")
        if u["totp_enabled"]:
            ticket = sec.new_token()
            self.db.x("INSERT INTO challenges(token_hash,user_id,expires,ip,ua) VALUES(?,?,?,?,?)", (sec.token_hash(ticket), u["id"], self.clock() + 300, ip, (ua or "")[:200]))
            raise TwoFactorRequired(ticket)
        self.db.event(u["id"], "login_sso")
        return self._new_session(u, ip, ua)

    # ------------------------------------------------------------------ e-mail verification
    def _send_verification(self, uid: int, email: str, name: str) -> None:
        t = sec.new_token()
        self.db.x("INSERT INTO verifications(token_hash,user_id,expires) VALUES(?,?,?)", (sec.token_hash(t), uid, self.clock() + 3 * 86400))
        self._mail(email, "Confirm your e-mail address", f"Hello {name},\n\nConfirm your address to unlock API keys and jobs:\n{self.public_url}/#/verify/{t}\n\nThe link works for three days.\n")

    def verify_email(self, token: str) -> dict:
        r = self.db.one("SELECT * FROM verifications WHERE token_hash=?", (sec.token_hash(token or ""),))
        if not r or r["expires"] < self.clock():
            raise ApiError(400, "this verification link is invalid or expired")
        self.db.x("UPDATE users SET email_verified=1 WHERE id=?", (r["user_id"],))
        self.db.x("DELETE FROM verifications WHERE user_id=?", (r["user_id"],))
        self.db.event(r["user_id"], "email_verified")
        return self.user_view(self.db.one("SELECT * FROM users WHERE id=?", (r["user_id"],)))

    def resend_verification(self, user) -> None:
        if user["email_verified"]:
            raise ApiError(400, "this address is already verified")
        if not self.reset_limit.allow(f"verify|{user['id']}"):
            raise ApiError(429, "too many requests; try later")
        self._send_verification(user["id"], user["email"], user["name"])

    def login(self, email: str, password: str, ip: str = "", ua: str = "") -> tuple[str, str, dict]:
        email = (email or "").strip().lower()
        if not self.login_limit.allow(f"{ip}|{email}") or not self.login_limit.allow(f"ip|{ip}"):
            raise ApiError(429, "too many attempts; try again in a few minutes")
        u = self.db.one("SELECT * FROM users WHERE email=?", (email,))
        now = self.clock()
        if u is not None and u["locked_until"] > now:
            raise ApiError(429, "account temporarily locked after repeated failures; try again later")
        ok = sec.verify_password(password or "", u["pw_hash"] if u else sec.DUMMY_HASH)     # same work for unknown accounts
        if not u or not ok:
            if u:
                failed = u["failed"] + 1
                self.db.x("UPDATE users SET failed=?, locked_until=? WHERE id=?", (failed, now + 900 if failed >= 5 else 0, u["id"]))
                self.db.event(u["id"], "login_failed")
            raise ApiError(401, "wrong e-mail or password")
        self.db.x("UPDATE users SET failed=0, locked_until=0 WHERE id=?", (u["id"],))
        if u["totp_enabled"]:                                                            # password right, second factor still needed
            ticket = sec.new_token()
            self.db.x("INSERT INTO challenges(token_hash,user_id,expires,ip,ua) VALUES(?,?,?,?,?)", (sec.token_hash(ticket), u["id"], now + 300, ip, (ua or "")[:200]))
            raise TwoFactorRequired(ticket)
        return self._new_session(u, ip, ua)

    def _new_session(self, u, ip: str, ua: str) -> tuple[str, str, dict]:
        now = self.clock()
        token, csrf = sec.new_token(), sec.new_token()
        self.db.x("INSERT INTO sessions(token_hash,user_id,csrf,created,expires,ip,ua) VALUES(?,?,?,?,?,?,?)",
                  (sec.token_hash(token), u["id"], csrf, now, now + SESSION_TTL_S, ip, (ua or "")[:200]))
        self.db.event(u["id"], "login")
        return token, csrf, self.user_view(u)

    def login_2fa(self, ticket: str, code: str, ip: str = "", ua: str = "") -> tuple[str, str, dict]:
        """Second step: a 6-digit code from the authenticator app, or one recovery code. Five tries per ticket, five minutes."""
        ch = self.db.one("SELECT * FROM challenges WHERE token_hash=?", (sec.token_hash(ticket or ""),))
        if not ch or ch["expires"] < self.clock() or ch["attempts"] >= 5:
            if ch:
                self.db.x("DELETE FROM challenges WHERE token_hash=?", (ch["token_hash"],))
            raise ApiError(401, "this sign-in attempt expired: start again")
        u = self.db.one("SELECT * FROM users WHERE id=?", (ch["user_id"],))
        self.db.x("UPDATE challenges SET attempts=attempts+1 WHERE token_hash=?", (ch["token_hash"],))
        step = totp_mod.verify(u["totp_secret"], code, u["totp_last_step"], self.clock())
        if step is not None:
            self.db.x("UPDATE users SET totp_last_step=? WHERE id=?", (step, u["id"]))
        else:
            codes = json.loads(u["recovery"])
            h = totp_mod.hash_code(code or "")
            if h not in codes:
                self.db.event(u["id"], "login_2fa_failed")
                raise ApiError(401, "wrong code")
            codes.remove(h)                                                              # a recovery code works once
            self.db.x("UPDATE users SET recovery=? WHERE id=?", (json.dumps(codes), u["id"]))
            self.db.event(u["id"], "recovery_code_used")
        self.db.x("DELETE FROM challenges WHERE token_hash=?", (ch["token_hash"],))
        return self._new_session(u, ip, ua)

    # ------------------------------------------------------------------ two-factor setup
    def totp_setup(self, user) -> dict:
        if user["totp_enabled"]:
            raise ApiError(400, "two-factor sign-in is already on")
        secret = totp_mod.new_secret()
        self.db.x("UPDATE users SET totp_secret=? WHERE id=?", (secret, user["id"]))
        from . import qr
        uri = totp_mod.uri(secret, user["email"])
        return {"secret": secret, "uri": uri, "qr_svg": qr.svg(uri), "digits": 6, "period": totp_mod.STEP}

    def totp_enable(self, user, code: str) -> dict:
        u = self.db.one("SELECT * FROM users WHERE id=?", (user["id"],))
        if u["totp_enabled"] or not u["totp_secret"]:
            raise ApiError(400, "start the setup first")
        step = totp_mod.verify(u["totp_secret"], code, 0, self.clock())
        if step is None:
            raise ApiError(400, "wrong code: check the time on your phone and try again")
        codes = totp_mod.new_recovery_codes()
        self.db.x("UPDATE users SET totp_enabled=1, totp_last_step=?, recovery=? WHERE id=?", (step, json.dumps([totp_mod.hash_code(c) for c in codes]), u["id"]))
        self.db.event(u["id"], "2fa_enabled")
        return {"recovery_codes": codes, "shown_once": True}

    def totp_disable(self, user, password: str, code: str) -> None:
        u = self.db.one("SELECT * FROM users WHERE id=?", (user["id"],))
        if not sec.verify_password(password or "", u["pw_hash"]):
            raise ApiError(403, "password is wrong")
        if not u["totp_enabled"]:
            raise ApiError(400, "two-factor sign-in is not on")
        step = totp_mod.verify(u["totp_secret"], code, u["totp_last_step"], self.clock())
        if step is None and totp_mod.hash_code(code or "") not in json.loads(u["recovery"]):
            raise ApiError(403, "wrong code")
        self.db.x("UPDATE users SET totp_enabled=0, totp_secret=NULL, recovery='[]' WHERE id=?", (u["id"],))
        self.db.x("DELETE FROM sessions WHERE user_id=?", (u["id"],))                    # sign out everywhere: the account just got weaker
        self.db.event(u["id"], "2fa_disabled")

    def session(self, token: str | None):
        """(user row, csrf) for a valid session token, else None."""
        if not token:
            return None
        s = self.db.one("SELECT * FROM sessions WHERE token_hash=?", (sec.token_hash(token),))
        if not s or s["expires"] < self.clock():
            return None
        u = self.db.one("SELECT * FROM users WHERE id=?", (s["user_id"],))
        return (u, s["csrf"]) if u else None

    def logout(self, token: str | None) -> None:
        if token:
            self.db.x("DELETE FROM sessions WHERE token_hash=?", (sec.token_hash(token),))

    def change_password(self, user, current: str, new: str, keep_token: str | None = None) -> None:
        if not sec.verify_password(current or "", user["pw_hash"]):
            raise ApiError(403, "current password is wrong")
        bad = sec.check_password_policy(new or "", user["email"])
        if bad:
            raise ApiError(400, bad)
        self.db.x("UPDATE users SET pw_hash=? WHERE id=?", (sec.hash_password(new), user["id"]))
        keep = sec.token_hash(keep_token) if keep_token else ""
        self.db.x("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user["id"], keep))      # sign out everywhere else
        self.db.event(user["id"], "password_changed")

    def reset_request(self, email: str, ip: str = "") -> None:
        """Always succeeds from the caller's point of view: no way to learn which e-mails have accounts."""
        email = (email or "").strip().lower()
        if not self.reset_limit.allow(ip or "?"):
            raise ApiError(429, "too many requests; try later")
        u = self.db.one("SELECT * FROM users WHERE email=?", (email,))
        if not u:
            return
        t = sec.new_token()
        self.db.x("INSERT INTO resets(token_hash,user_id,expires) VALUES(?,?,?)", (sec.token_hash(t), u["id"], self.clock() + 3600))
        self._mail(email, "Reset your password", f"Use this link within one hour:\n{self.public_url}/#/reset/{t}\n\nIf you did not ask for it, ignore this message.\n")

    def reset_confirm(self, token: str, new: str) -> None:
        r = self.db.one("SELECT * FROM resets WHERE token_hash=?", (sec.token_hash(token or ""),))
        if not r or r["used"] or r["expires"] < self.clock():
            raise ApiError(400, "this reset link is invalid or expired")
        u = self.db.one("SELECT * FROM users WHERE id=?", (r["user_id"],))
        bad = sec.check_password_policy(new or "", u["email"])
        if bad:
            raise ApiError(400, bad)
        self.db.x("UPDATE resets SET used=1 WHERE token_hash=?", (r["token_hash"],))
        self.db.x("UPDATE users SET pw_hash=?, failed=0, locked_until=0 WHERE id=?", (sec.hash_password(new), u["id"]))
        self.db.x("DELETE FROM sessions WHERE user_id=?", (u["id"],))
        self.db.event(u["id"], "password_reset")

    def _mail(self, to: str, subject: str, body: str) -> None:
        self.mailer.queue(to, subject, body)

    # ------------------------------------------------------------------ organisations, members, invitations
    def org_view(self, org_id: int, c: Ctx | None = None) -> dict:
        o = self.db.one("SELECT * FROM orgs WHERE id=?", (org_id,))
        out = {"id": o["id"], "name": o["name"], "personal": bool(o["personal"]), "created": o["created"],
               "members": self.db.one("SELECT COUNT(*) c FROM members WHERE org_id=?", (org_id,))["c"]}
        if c is not None:
            out["role"] = c["role"]
        return out

    def list_orgs(self, user) -> list[dict]:
        rows = self.db.q("SELECT o.id, m.role FROM orgs o JOIN members m ON m.org_id=o.id WHERE m.user_id=? ORDER BY o.personal DESC, o.id", (user["id"],))
        return [{**self.org_view(r["id"]), "role": r["role"]} for r in rows]

    def create_org(self, user, name: str) -> dict:
        c0 = self._c(user)
        self._need_verified(c0)
        name = (name or "").strip()
        if not 1 <= len(name) <= 60:
            raise ApiError(400, "organization name must be 1 to 60 characters")
        if self.db.one("SELECT COUNT(*) c FROM members WHERE user_id=? AND role='owner'", (user["id"],))["c"] >= 10:
            raise ApiError(400, "limit of 10 organizations owned reached")
        oid = self.db.x("INSERT INTO orgs(name,created,personal) VALUES(?,?,0)", (name, self.clock()))
        self.db.x("INSERT INTO members(org_id,user_id,role,created) VALUES(?,?,?,?)", (oid, user["id"], "owner", self.clock()))
        self.db.event(user["id"], "org_created", str(oid))
        return {**self.org_view(oid), "role": "owner"}

    def org_detail(self, c: Ctx) -> dict:
        o = self.db.one("SELECT * FROM orgs WHERE id=?", (c.org_id,))
        members = [{"user_id": m["user_id"], "email": m["email"], "name": m["name"], "role": m["role"], "since": m["created"], "apps": None if m["app_ids"] is None else json.loads(m["app_ids"])} for m in
                   self.db.q("SELECT m.user_id, m.role, m.created, m.app_ids, u.email, u.name FROM members m JOIN users u ON u.id=m.user_id WHERE m.org_id=? ORDER BY m.created", (c.org_id,))]
        out = {**self.org_view(c.org_id, c), "my_apps": None if c["app_scope"] is None else sorted(c["app_scope"]),
               "app_list": [{"id": a["id"], "name": a["name"]} for a in self.db.q("SELECT id,name FROM apps WHERE org_id=? AND deleted IS NULL ORDER BY id", (c.org_id,)) if c["app_scope"] is None or a["id"] in c["app_scope"]],
               "member_list": members, "perms": sorted(c["perms"]), "roles": self.list_roles(c), "permission_help": PERMS}
        if self._has(c, "members.manage") or self._has(c, "org.manage"):
            out["invites"] = [{"id": i["id"], "email": i["email"], "role": i["role"], "expires": i["expires"]} for i in
                              self.db.q("SELECT * FROM invites WHERE org_id=? AND accepted IS NULL AND expires>? ORDER BY id DESC", (c.org_id, self.clock()))]
            out["billing"] = {"name": o["billing_name"], "address": o["billing_address"], "country": o["billing_country"], "vat_id": o["vat_id"], "vat_status": o["vat_status"],
                              "city": o["billing_city"], "postal_code": o["billing_postal"], "email": o["billing_email"]}
        return out

    def update_org(self, c: Ctx, name=None, billing: dict | None = None) -> dict:
        self._need(c, "org.manage")
        if name is not None:
            if not 1 <= len(name.strip()) <= 60:
                raise ApiError(400, "organization name must be 1 to 60 characters")
            self.db.x("UPDATE orgs SET name=? WHERE id=?", (name.strip(), c.org_id))
        if billing is not None:
            f = {"name": (billing.get("name") or "")[:120], "address": (billing.get("address") or "")[:400], "country": (billing.get("country") or "").strip().upper()[:2], "vat_id": (billing.get("vat_id") or "").strip()[:40],
                 "city": (billing.get("city") or "").strip()[:80], "postal": (billing.get("postal_code") or "").strip()[:20], "email": (billing.get("email") or "").strip()[:120]}
            if f["email"] and not sec.valid_email(f["email"]):
                raise ApiError(400, "enter a valid billing e-mail address")
            if f["country"] and not f["country"].isalpha():
                raise ApiError(400, "country must be a 2-letter code")
            status = ""
            if f["vat_id"]:
                r = vat_mod.check(f["vat_id"])
                if not r["ok"]:
                    raise ApiError(400, "VAT id: " + r["reason"])
                f["vat_id"] = r["country"] + r["number"]
                status = "format ok" if r["checksum"] in ("ok", "not checked for this country") else "format ok"
                if r["checksum"] == "ok":
                    status = "format and check digit ok"
                if self.pricing.data.get("check_vat_with_vies"):
                    v = vat_mod.vies(f["vat_id"], self.vies_base)
                    if v is False:
                        raise ApiError(400, "VIES (European Commission) says this VAT number is not registered")
                    status = "registered (VIES)" if v else status + ", VIES unreachable"
            self.db.x("UPDATE orgs SET billing_name=?, billing_address=?, billing_country=?, vat_id=?, vat_status=?, billing_city=?, billing_postal=?, billing_email=? WHERE id=?",
                      (f["name"], f["address"], f["country"], f["vat_id"], status, f["city"], f["postal"], f["email"], c.org_id))
        return self.org_detail(c)

    def delete_org(self, c: Ctx) -> None:
        self._need(c, "org.delete")
        if self.db.one("SELECT personal FROM orgs WHERE id=?", (c.org_id,))["personal"]:
            raise ApiError(400, "a personal workspace cannot be deleted; delete your account instead")
        self._drop_org(c.org_id, c)

    def _drop_org(self, org_id: int, actor) -> None:
        if self.db.one("SELECT 1 FROM invoices WHERE org_id=? AND status='open'", (org_id,)):
            raise ApiError(409, "pay or settle the open invoices first")
        for a in self.db.q("SELECT id FROM apps WHERE org_id=?", (org_id,)):
            for k in self.db.q("SELECT * FROM api_keys WHERE app_id=? AND revoked IS NULL", (a["id"],)):
                self._revoke(k)
            for t in ("usage", "api_keys"):
                self.db.x(f"DELETE FROM {t} WHERE app_id=?", (a["id"],))
        for t in ("apps", "members", "invites", "invoices"):
            self.db.x(f"DELETE FROM {t} WHERE org_id=?", (org_id,))
        self.db.x("DELETE FROM orgs WHERE id=?", (org_id,))
        self.db.event(actor["id"], "org_deleted", str(org_id))

    def _check_scope(self, c: Ctx, apps) -> str | None:
        """Validate an app list for an invitation or a member: only apps of this organization, and never more than the giver can see."""
        if apps is None:
            if c["app_scope"] is not None:
                raise ApiError(403, "you can only share the apps you can see yourself: choose the apps explicitly")
            return None
        if not isinstance(apps, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in apps):
            raise ApiError(400, "apps must be a list of app ids")
        ok = {a["id"] for a in self.db.q("SELECT id FROM apps WHERE org_id=? AND deleted IS NULL", (c.org_id,))}
        if not set(apps) <= ok:
            raise ApiError(404, "app not found")
        if c["app_scope"] is not None and not set(apps) <= c["app_scope"]:
            raise ApiError(403, "you cannot share apps you cannot see yourself")
        return json.dumps(sorted(set(apps)))

    def invite(self, c: Ctx, email: str, role: str, apps=None) -> dict:
        self._need(c, "members.manage")
        self._need_verified(c)
        email = (email or "").strip().lower()
        if not sec.valid_email(email):
            raise ApiError(400, "enter a valid e-mail address")
        self._may_grant(c, role)
        scope = self._check_scope(c, apps)
        if self.db.one("SELECT personal FROM orgs WHERE id=?", (c.org_id,))["personal"]:
            raise ApiError(400, "a personal workspace has one member: create an organization to work with others")
        if self.db.one("SELECT COUNT(*) c FROM members WHERE org_id=?", (c.org_id,))["c"] >= 25:
            raise ApiError(400, "limit of 25 members reached")
        if self.db.one("SELECT 1 FROM members m JOIN users u ON u.id=m.user_id WHERE m.org_id=? AND u.email=?", (c.org_id, email)):
            raise ApiError(409, "this person is already a member")
        t = sec.new_token()
        iid = self.db.x("INSERT INTO invites(org_id,email,role,token_hash,invited_by,created,expires,app_ids) VALUES(?,?,?,?,?,?,?,?)",
                        (c.org_id, email, role, sec.token_hash(t), c["id"], self.clock(), self.clock() + 7 * 86400, scope))
        org = self.db.one("SELECT name FROM orgs WHERE id=?", (c.org_id,))["name"]
        self._mail(email, f"{c['name']} invited you to {org}", f"{c['name']} invited you to join \"{org}\" as {role}.\n\nSign in or create an account with this address, then open:\n{self.public_url}/#/invite/{t}\n\nThe invitation works for seven days.\n")
        self.db.event(c["id"], "member_invited", f"{c.org_id} {email} {role}")
        return {"id": iid, "email": email, "role": role, "apps": None if scope is None else json.loads(scope)}

    def set_member_apps(self, c: Ctx, user_id: int, apps) -> None:
        """Limit a member to some apps (a list of app ids) or give them all apps (None, only if the giver has all apps themselves)."""
        self._need(c, "members.manage")
        m = self.db.one("SELECT role FROM members WHERE org_id=? AND user_id=?", (c.org_id, user_id))
        if not m:
            raise ApiError(404, "member not found")
        if m["role"] == "owner" and "members.owner" not in c["perms"]:
            raise ApiError(403, "only an owner can change an owner")
        self.db.x("UPDATE members SET app_ids=? WHERE org_id=? AND user_id=?", (self._check_scope(c, apps), c.org_id, user_id))
        self.db.event(c["id"], "member_apps", f"{c.org_id} {user_id}")

    def revoke_invite(self, c: Ctx, invite_id: int) -> None:
        self._need(c, "members.manage")
        self.db.x("DELETE FROM invites WHERE id=? AND org_id=?", (invite_id, c.org_id))

    def accept_invite(self, user, token: str) -> dict:
        i = self.db.one("SELECT * FROM invites WHERE token_hash=?", (sec.token_hash(token or ""),))
        if not i or i["accepted"] is not None or i["expires"] < self.clock():
            raise ApiError(400, "this invitation is invalid or expired")
        if i["email"] != user["email"].lower():
            raise ApiError(403, f"this invitation was sent to another address ({i['email'][:2]}…): sign in with that account")
        self.db.x("INSERT OR IGNORE INTO members(org_id,user_id,role,created,app_ids) VALUES(?,?,?,?,?)", (i["org_id"], user["id"], i["role"], self.clock(), i["app_ids"]))
        self.db.x("UPDATE invites SET accepted=? WHERE id=?", (self.clock(), i["id"]))
        self.db.event(user["id"], "invite_accepted", str(i["org_id"]))
        return {**self.org_view(i["org_id"]), "role": i["role"]}

    def set_member_role(self, c: Ctx, user_id: int, role: str) -> None:
        self._need(c, "members.manage")
        m = self.db.one("SELECT role FROM members WHERE org_id=? AND user_id=?", (c.org_id, user_id))
        if not m:
            raise ApiError(404, "member not found")
        self._may_grant(c, role)                                                    # also covers "only an owner can make an owner"
        if m["role"] == "owner" and "members.owner" not in c["perms"]:
            raise ApiError(403, "only an owner can change an owner")
        if m["role"] == "owner" and role != "owner" and self.db.one("SELECT COUNT(*) c FROM members WHERE org_id=? AND role='owner'", (c.org_id,))["c"] <= 1:
            raise ApiError(409, "an organization needs at least one owner")
        self.db.x("UPDATE members SET role=? WHERE org_id=? AND user_id=?", (role, c.org_id, user_id))
        self.db.event(c["id"], "member_role", f"{c.org_id} {user_id} {role}")

    def remove_member(self, c: Ctx, user_id: int) -> None:
        """Someone with members.manage removes a member, or anyone leaves (user_id is their own id)."""
        if user_id != c["id"]:
            self._need(c, "members.manage")
        m = self.db.one("SELECT role FROM members WHERE org_id=? AND user_id=?", (c.org_id, user_id))
        if not m:
            raise ApiError(404, "member not found")
        if m["role"] == "owner" and "members.owner" not in c["perms"]:
            raise ApiError(403, "only an owner can remove an owner")
        if m["role"] == "owner" and self.db.one("SELECT COUNT(*) c FROM members WHERE org_id=? AND role='owner'", (c.org_id,))["c"] <= 1:
            raise ApiError(409, "an organization needs at least one owner: make someone else owner first")
        if self.db.one("SELECT personal FROM orgs WHERE id=?", (c.org_id,))["personal"]:
            raise ApiError(400, "you cannot leave your personal workspace")
        self.db.x("DELETE FROM members WHERE org_id=? AND user_id=?", (c.org_id, user_id))
        self.db.event(c["id"], "member_removed", f"{c.org_id} {user_id}")

    # ------------------------------------------------------------------ custom roles
    def list_roles(self, c: Ctx) -> list[dict]:
        out = [{"name": n, "builtin": True, "perms": sorted(p)} for n, p in BUILTIN.items()]
        for r in self.db.q("SELECT * FROM org_roles WHERE org_id=? ORDER BY name", (c.org_id,)):
            out.append({"name": r["name"], "builtin": False, "perms": sorted(json.loads(r["perms"])),
                        "members": self.db.one("SELECT COUNT(*) c FROM members WHERE org_id=? AND role=?", (c.org_id, r["name"]))["c"]})
        return out

    def create_role(self, c: Ctx, name: str, perms: list) -> dict:
        self._need(c, "members.manage")
        name = (name or "").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,29}", name) or name in BUILTIN:
            raise ApiError(400, "role names are 1 to 30 lowercase letters, digits or dashes and cannot be viewer, member, admin or owner")
        if not isinstance(perms, list) or not perms or any(p not in PERMS for p in perms):
            raise ApiError(400, "choose permissions from: " + ", ".join(PERMS))
        if "org.delete" in perms or "members.owner" in perms:
            raise ApiError(400, "org.delete and members.owner belong to the owner role only")
        if not frozenset(perms) <= c["perms"]:
            raise ApiError(403, "you cannot define a role with permissions you do not have yourself")
        if self.db.one("SELECT COUNT(*) c FROM org_roles WHERE org_id=?", (c.org_id,))["c"] >= 10:
            raise ApiError(400, "limit of 10 custom roles reached")
        try:
            self.db.x("INSERT INTO org_roles(org_id,name,perms,created) VALUES(?,?,?,?)", (c.org_id, name, json.dumps(sorted(set(perms))), self.clock()))
        except Exception:
            raise ApiError(409, "this role already exists")
        self.db.event(c["id"], "role_created", f"{c.org_id} {name}")
        return {"name": name, "builtin": False, "perms": sorted(set(perms))}

    def delete_role(self, c: Ctx, name: str) -> None:
        self._need(c, "members.manage")
        if self.db.one("SELECT 1 FROM members WHERE org_id=? AND role=?", (c.org_id, name)) or self.db.one("SELECT 1 FROM invites WHERE org_id=? AND role=? AND accepted IS NULL", (c.org_id, name)):
            raise ApiError(409, "members or pending invitations still have this role")
        self.db.x("DELETE FROM org_roles WHERE org_id=? AND name=?", (c.org_id, name))

    # ------------------------------------------------------------------ apps and keys (scoped to the organisation)
    def _app(self, user, app_id: int):
        c = self._c(user)
        a = self.db.one("SELECT * FROM apps WHERE id=? AND org_id=? AND deleted IS NULL", (app_id, c.org_id))
        if not a or (c["app_scope"] is not None and a["id"] not in c["app_scope"]):
            raise ApiError(404, "app not found")                       # same answer for "not yours", "not in your scope" and "does not exist"
        return a

    def app_view(self, a) -> dict:
        keys = [self.key_view(k) for k in self.db.q("SELECT * FROM api_keys WHERE app_id=? ORDER BY id", (a["id"],))]
        month = self._app_seconds(a["id"], period_of(self.clock()))
        cost = self.pricing.rate({a["id"]: month})["total_usd"]
        over = a["budget_usd"] is not None and cost >= a["budget_usd"]
        return {"id": a["id"], "name": a["name"], "description": a["description"], "created": a["created"], "budget_usd": a["budget_usd"],
                "tenant": f"app{a['id']}", "keys": keys, "month_seconds": month, "month_cost_usd_if_alone": cost, "over_budget": over}

    @staticmethod
    def key_view(k) -> dict:
        return {"id": k["id"], "name": k["name"], "kind": k["kind"], "hint": k["hint"], "created": k["created"], "expires": k["expires"],
                "revoked": k["revoked"] is not None}

    def create_app(self, user, name: str, description: str = "", budget_usd=None) -> dict:
        c = self._c(user)
        self._need(c, "apps.write")
        name = (name or "").strip()
        if not 1 <= len(name) <= 60:
            raise ApiError(400, "app name must be 1 to 60 characters")
        if self.db.one("SELECT COUNT(*) c FROM apps WHERE org_id=? AND deleted IS NULL", (c.org_id,))["c"] >= MAX_APPS:
            raise ApiError(400, f"limit of {MAX_APPS} apps reached")
        if budget_usd is not None and not (isinstance(budget_usd, (int, float)) and 0 <= budget_usd <= 1e6):
            raise ApiError(400, "budget must be a number between 0 and 1,000,000")
        aid = self.db.x("INSERT INTO apps(user_id,org_id,name,description,budget_usd,created) VALUES(?,?,?,?,?,?)",
                        (c["id"], c.org_id, name, (description or "")[:300], budget_usd, self.clock()))
        if c["app_scope"] is not None:                                  # a scoped member sees the apps they create
            ids = sorted(c["app_scope"] | {aid})
            self.db.x("UPDATE members SET app_ids=? WHERE org_id=? AND user_id=?", (json.dumps(ids), c.org_id, c["id"]))
            c = Ctx({**c, "app_scope": frozenset(ids)})
        self.db.event(c["id"], "app_created", str(aid))
        return self.app_view(self._app(c, aid))

    def list_apps(self, user) -> list[dict]:
        c = self._c(user)
        return [self.app_view(a) for a in self.db.q("SELECT * FROM apps WHERE org_id=? AND deleted IS NULL ORDER BY id", (c.org_id,))
                if c["app_scope"] is None or a["id"] in c["app_scope"]]

    def delete_app(self, user, app_id: int) -> None:
        c = self._c(user)
        self._need(c, "apps.delete")
        a = self._app(c, app_id)
        for k in self.db.q("SELECT * FROM api_keys WHERE app_id=? AND revoked IS NULL", (a["id"],)):
            self._revoke(k)
        self.db.x("UPDATE apps SET deleted=? WHERE id=?", (self.clock(), a["id"]))
        self.db.event(c["id"], "app_deleted", str(a["id"]))

    def update_app(self, user, app_id: int, name=None, description=None, budget_usd="keep") -> dict:
        c = self._c(user)
        self._need(c, "apps.write")
        a = self._app(c, app_id)
        if name is not None:
            if not 1 <= len(name.strip()) <= 60:
                raise ApiError(400, "app name must be 1 to 60 characters")
            self.db.x("UPDATE apps SET name=? WHERE id=?", (name.strip(), a["id"]))
        if description is not None:
            self.db.x("UPDATE apps SET description=? WHERE id=?", (description[:300], a["id"]))
        if budget_usd != "keep":
            if budget_usd is not None and not (isinstance(budget_usd, (int, float)) and 0 <= budget_usd <= 1e6):
                raise ApiError(400, "budget must be a number between 0 and 1,000,000")
            self._need(c, "apps.budget")                                      # the spending limit belongs to the people who pay
            self.db.x("UPDATE apps SET budget_usd=? WHERE id=?", (budget_usd, a["id"]))
        return self.app_view(self._app(c, app_id))

    def create_key(self, user, app_id: int, name: str, kind: str = "client", ttl_days: int = 90) -> dict:
        """Returns the key ONCE: only a hint (last 4 characters) is stored."""
        c = self._c(user)
        self._need(c, "keys.write")
        self._need_verified(c)
        a = self._app(c, app_id)
        if kind not in KEY_KINDS:
            raise ApiError(400, f"key kind must be one of {', '.join(KEY_KINDS)}")
        name = (name or "").strip()
        if not 1 <= len(name) <= 60:
            raise ApiError(400, "key name must be 1 to 60 characters")
        if not isinstance(ttl_days, int) or not 1 <= ttl_days <= 365:
            raise ApiError(400, "key lifetime must be 1 to 365 days")
        if self.db.one("SELECT COUNT(*) c FROM api_keys WHERE app_id=? AND revoked IS NULL", (a["id"],))["c"] >= MAX_KEYS_PER_APP:
            raise ApiError(400, f"limit of {MAX_KEYS_PER_APP} active keys per app reached")
        if self.auth is None:
            raise ApiError(503, "this server has no hub master key: keys cannot be issued")
        now = self.clock()
        kid = self.db.x("INSERT INTO api_keys(app_id,name,kind,cred_name,hint,created,expires) VALUES(?,?,?,?,?,?,?)",
                        (a["id"], name, kind, "", "", now, now + ttl_days * 86400))
        cred_name = f"app{a['id']}:k{kid}"
        token = self.auth.issue(cred_name, KEY_KINDS[kind], ttl_s=ttl_days * 86400)
        self.db.x("UPDATE api_keys SET cred_name=?, hint=? WHERE id=?", (cred_name, token[-4:], kid))
        self.db.event(c["id"], "key_created", f"{a['id']}/{kid}")
        return {**self.key_view(self.db.one("SELECT * FROM api_keys WHERE id=?", (kid,))), "token": token,
                "hub": self.hub_public, "shown_once": True}

    def _revoke(self, k) -> None:
        self.db.x("UPDATE api_keys SET revoked=? WHERE id=?", (self.clock(), k["id"]))
        if self.auth is not None:
            self.auth.revoke(k["cred_name"])
        if self.revoked_path:
            with open(self.revoked_path, "a") as f:                  # the hub re-reads this file
                f.write(k["cred_name"] + "\n")

    def revoke_key(self, user, app_id: int, key_id: int) -> None:
        c = self._c(user)
        self._need(c, "keys.write")
        a = self._app(c, app_id)
        k = self.db.one("SELECT * FROM api_keys WHERE id=? AND app_id=?", (key_id, a["id"]))
        if not k:
            raise ApiError(404, "key not found")
        if k["revoked"] is None:
            self._revoke(k)
            self.db.event(c["id"], "key_revoked", f"{a['id']}/{key_id}")

    # ------------------------------------------------------------------ usage
    def ingest_usage(self) -> int:
        """Read new lines of the hub's usage file into the database. Returns the number of rows added."""
        if not self.usage_path or not os.path.exists(self.usage_path):
            return 0
        off = self.db.one("SELECT value FROM offsets WHERE name='usage'")
        pos = off["value"] if off else 0
        size = os.path.getsize(self.usage_path)
        if size < pos:
            pos = 0                                                    # the file was rotated or truncated
        with open(self.usage_path, "rb") as f:
            f.seek(pos)
            data = f.read()
        end = data.rfind(b"\n") + 1                                    # never read a half-written last line
        added = 0
        with self.db.lock:
            for line in data[:end].splitlines():
                try:
                    e = json.loads(line)
                    tenant = str(e["tenant"])
                    if not tenant.startswith("app"):
                        continue
                    app_id = int(tenant[3:])
                    if not self.db.one("SELECT 1 FROM apps WHERE id=?", (app_id,)):
                        continue
                    self.db.x("INSERT INTO usage(app_id,ts,workload,node,ok,seconds) VALUES(?,?,?,?,?,?)",
                              (app_id, float(e["ts"]), str(e.get("workload", ""))[:60], str(e.get("node", ""))[:60], 1 if e.get("ok") else 0, max(0.0, float(e.get("wall_s") or 0))))
                    added += 1
                except (ValueError, KeyError, TypeError):
                    continue                                           # a bad line never stops metering
            self.db.x("INSERT INTO offsets(name,value) VALUES('usage',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (pos + end,))
        return added

    def _app_seconds(self, app_id: int, period: str) -> float:
        a, b = period_bounds(period)
        return self.db.one("SELECT COALESCE(SUM(seconds),0) s FROM usage WHERE app_id=? AND ts>=? AND ts<?", (app_id, a, b))["s"]

    def usage_for_app(self, user, app_id: int, days: int = 30) -> dict:
        a = self._app(user, app_id)
        self.ingest_usage()
        days = max(1, min(int(days), 365))
        since = self.clock() - days * 86400
        rows = self.db.q("SELECT ts, seconds, ok, workload, node FROM usage WHERE app_id=? AND ts>=? ORDER BY ts", (a["id"], since))
        by_day: dict[str, dict] = {}
        for r in rows:
            d = datetime.fromtimestamp(r["ts"], timezone.utc).strftime("%Y-%m-%d")
            x = by_day.setdefault(d, {"day": d, "tasks": 0, "seconds": 0.0, "failed": 0})
            x["tasks"] += 1; x["seconds"] += r["seconds"]; x["failed"] += 0 if r["ok"] else 1
        recent = [{"ts": r["ts"], "workload": r["workload"], "node": r["node"], "ok": bool(r["ok"]), "seconds": r["seconds"]} for r in rows[-15:]][::-1]
        return {"app_id": a["id"], "days": days, "tasks": len(rows), "seconds": sum(r["seconds"] for r in rows),
                "by_day": sorted(by_day.values(), key=lambda x: x["day"]), "recent": recent}

    # ------------------------------------------------------------------ billing (per organisation)
    def _seconds_by_app(self, user, period: str) -> dict[int, float]:
        c = self._c(user)
        out = {}
        for a in self.db.q("SELECT id FROM apps WHERE org_id=? ORDER BY id", (c.org_id,)):       # deleted apps still count: usage happened
            s = self._app_seconds(a["id"], period)
            if s > 0:
                out[a["id"]] = s
        return out

    def _tax_for(self, org) -> tuple[float, str]:
        p = self.pricing.data
        seller = self.company()
        country = (org["billing_country"] or "").upper()
        rate = float(p["tax_by_country"].get(country, p["tax_rate_percent"]))
        if p.get("no_tax_with_vat_id_abroad") and org["vat_id"] and country and seller.get("country") and country != seller["country"].upper():
            return 0.0, rules.reverse_charge_text(seller["country"])
        return rate, ""

    def _rate_org(self, c: Ctx, period: str) -> dict:
        r = self.pricing.rate(self._seconds_by_app(c, period))
        org = self.db.one("SELECT * FROM orgs WHERE id=?", (c.org_id,))
        rate, note = self._tax_for(org)
        tax = round(r["total_usd"] * rate / 100, 4)
        return {**r, "subtotal_usd": r["total_usd"], "tax_rate": rate, "tax_usd": tax, "total_usd": round(r["total_usd"] + tax, 4), "tax_label": self.pricing.data["tax_label"], "tax_note": note}

    def billing(self, user) -> dict:
        c = self._c(user)
        self._need(c, "billing.read")
        self.ingest_usage()
        self._finalize_past(c)
        cur = period_of(self.clock())
        est = self._rate_org(c, cur)
        names = {a["id"]: a["name"] for a in self.db.q("SELECT id,name FROM apps WHERE org_id=?", (c.org_id,))}
        for l in est["lines"]:
            l["app"] = names.get(l["app_id"], f"app{l['app_id']}")
        inv = [{"id": i["id"], "number": i["number"], "period": i["period"], "amount_usd": i["amount_usd"], "subtotal_usd": i["subtotal_usd"], "tax_usd": i["tax_usd"],
                "tax_rate": i["tax_rate"], "status": i["status"], "paid": i["paid"], "lines": json.loads(i["lines"])}
               for i in self.db.q("SELECT * FROM invoices WHERE org_id=? ORDER BY period DESC", (c.org_id,))]
        credits = [{"id": n["id"], "number": n["number"], "invoice_id": n["invoice_id"], "total_usd": n["total_usd"], "reason": n["reason"], "created": n["created"], "status": n["status"]}
                   for n in self.db.q("SELECT * FROM credit_notes WHERE org_id=? ORDER BY id DESC", (c.org_id,))]
        return {"period": cur, "estimate": est, "pricing": self.pricing.data, "pricing_is_default": self.pricing_is_default, "invoices": inv, "credit_notes": credits,
                "payments_enabled": self.stripe.configured, "org": self.org_view(c.org_id, c)}

    def _next_invoice_number(self, ts: float) -> str:
        year = datetime.fromtimestamp(ts, timezone.utc).year
        with self.db.lock:
            self.db.x("INSERT INTO counters(name,value) VALUES(?,0) ON CONFLICT(name) DO NOTHING", (f"invoice-{year}",))
            self.db.x("UPDATE counters SET value=value+1 WHERE name=?", (f"invoice-{year}",))
            n = self.db.one("SELECT value FROM counters WHERE name=?", (f"invoice-{year}",))["value"]
        return f"INV-{year}-{n:05d}"                                          # gap-free, in order of creation

    def _finalize_past(self, c: Ctx) -> None:
        cur = period_of(self.clock())
        first = self.db.one("SELECT MIN(ts) t FROM usage u JOIN apps a ON a.id=u.app_id WHERE a.org_id=?", (c.org_id,))["t"]
        if first is None:
            return
        y, m = int(period_of(first)[:4]), int(period_of(first)[5:7])
        org = self.db.one("SELECT * FROM orgs WHERE id=?", (c.org_id,))
        while f"{y:04d}-{m:02d}" < cur:
            p = f"{y:04d}-{m:02d}"
            if not self.db.one("SELECT 1 FROM invoices WHERE org_id=? AND period=?", (c.org_id, p)):
                r = self._rate_org(c, p)
                if r["lines"]:
                    sub = r["subtotal_usd"]
                    status = "paid" if r["total_usd"] == 0 else ("waived" if sub < self.pricing.data["min_invoice_usd"] else "open")
                    number = self._next_invoice_number(self.clock()) if status == "open" else None
                    names = {a["id"]: a["name"] for a in self.db.q("SELECT id,name FROM apps WHERE org_id=?", (c.org_id,))}
                    lines = [{**l, "app": names.get(l["app_id"], f"app{l['app_id']}"), "usd_per_hour": self.pricing.data["compute_usd_per_hour"]} for l in r["lines"]]
                    billing = {"name": org["billing_name"] or org["name"], "address": org["billing_address"], "country": org["billing_country"], "vat_id": org["vat_id"],
                               "city": org["billing_city"], "postal_code": org["billing_postal"], "email": org["billing_email"]}
                    self.db.x("INSERT INTO invoices(user_id,org_id,period,amount_usd,status,lines,created,paid,number,subtotal_usd,tax_rate,tax_usd,billing,seller) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (c["id"], c.org_id, p, r["total_usd"] if status == "open" else 0.0, status, json.dumps(lines), self.clock(), self.clock() if status == "paid" else None,
                               number, sub if status == "open" else 0.0, r["tax_rate"], r["tax_usd"] if status == "open" else 0.0, json.dumps(billing), json.dumps({**self.company(), "tax_label": self.pricing.data["tax_label"], "currency": self.pricing.data["currency"], "tax_note": r["tax_note"], "reverse_charge": bool(r["tax_note"])})))
            m += 1
            if m == 13:
                y, m = y + 1, 1

    def pay(self, user, invoice_id: int) -> dict:
        c = self._c(user)
        self._need(c, "billing.pay")
        inv = self.db.one("SELECT * FROM invoices WHERE id=? AND org_id=?", (invoice_id, c.org_id))
        if not inv:
            raise ApiError(404, "invoice not found")
        if inv["status"] != "open":
            raise ApiError(400, "this invoice does not need payment")
        try:
            url, ref = self.stripe.checkout_url(inv["id"], inv["amount_usd"], c["email"], f"{self.public_url}/#/billing?paid=1", f"{self.public_url}/#/billing",
                                                self.pricing.data["currency"])
        except PaymentError as e:
            raise ApiError(503, str(e))
        self.db.x("UPDATE invoices SET provider_ref=? WHERE id=?", (ref, inv["id"]))
        return {"url": url}

    def _invoice_doc(self, i, credit=None) -> dict:
        """The data of one invoice (or credit note) in the form every renderer (PDF, UBL) needs."""
        seller = json.loads(i["seller"] or "{}") if credit is None else json.loads(self.db.one("SELECT seller FROM invoices WHERE id=?", (credit["invoice_id"],))["seller"] or "{}")
        inv = i if credit is None else self.db.one("SELECT * FROM invoices WHERE id=?", (credit["invoice_id"],))
        customer = json.loads(inv["billing"] or "{}")
        cur = seller.get("currency") or "usd"
        y, m = int(inv["period"][:4]), int(inv["period"][5:7])
        start = datetime(y, m, 1, tzinfo=timezone.utc)
        end = datetime(y + (m == 12), 1 if m == 12 else m + 1, 1, tzinfo=timezone.utc).timestamp() - 86400
        created = (credit or inv)["created"]
        terms = int(seller.get("payment_terms_days") or 30)
        due = datetime.fromtimestamp(inv["created"] + terms * 86400, timezone.utc).strftime("%Y-%m-%d")
        reverse = bool(seller.get("reverse_charge"))
        rate = inv["tax_rate"] or 0.0
        doc = {"kind": "credit" if credit else "invoice", "number": (credit or inv)["number"], "refers_to": inv["number"] if credit else None,
               "issued": datetime.fromtimestamp(created, timezone.utc).strftime("%Y-%m-%d"), "due": due, "period": inv["period"],
               "period_start": start.strftime("%Y-%m-%d"), "period_end": datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%d"),
               "status": (credit or inv)["status"], "seller": seller, "customer": customer, "currency": cur, "tax_rate": rate, "reverse_charge": reverse,
               "tax_exempt_note": seller.get("tax_exempt_note", ""), "buyer_reference": customer.get("name", "")}
        if credit:
            doc.update(lines=[{"description": ("Credit: " + credit["reason"])[:48], "qty": 1.0, "unit": "C62", "unit_price": credit["subtotal_usd"], "amount": credit["subtotal_usd"]}],
                       subtotal=credit["subtotal_usd"], tax=credit["tax_usd"], total=credit["total_usd"], note="This credit note reduces invoice " + inv["number"] + "."
                       + (" Refund due to the customer." if credit["status"] == "refund_due" else ""))
        else:
            lines = []
            for l in json.loads(inv["lines"]):
                if l["billable_seconds"] > 0:
                    h = l["billable_seconds"] / 3600
                    lines.append({"description": f"Compute: {l['app']}", "qty": h, "unit": "HUR", "unit_price": l.get("usd_per_hour", 0), "amount": l["usd"]})
            doc.update(lines=lines, subtotal=inv["subtotal_usd"] or 0.0, tax=inv["tax_usd"] or 0.0, total=inv["amount_usd"],
                       note="Free monthly allowance already deducted." if any(l["seconds"] > l["billable_seconds"] for l in json.loads(inv["lines"])) else "")
        doc["mentions"] = rules.mentions(seller, customer, rate, reverse, due)
        return doc

    def _document(self, user, kind: str, ident: int):
        c = self._c(user)
        self._need(c, "billing.read")
        if kind == "invoice":
            i = self.db.one("SELECT * FROM invoices WHERE id=? AND org_id=?", (ident, c.org_id))
            if not i or not i["number"]:
                raise ApiError(404, "invoice not found")
            return self._invoice_doc(i)
        n = self.db.one("SELECT * FROM credit_notes WHERE id=? AND org_id=?", (ident, c.org_id))
        if not n:
            raise ApiError(404, "credit note not found")
        return self._invoice_doc(n, credit=n)

    def invoice_pdf(self, user, invoice_id: int) -> tuple[bytes, str]:
        d = self._document(user, "invoice", invoice_id)
        return render_invoice({**d, "lines": [{"description": l["description"], "qty": f"{l['qty']:.3f} h", "unit": f"{l['unit_price']:g} {d['currency'].upper()}/h", "amount": l["amount"]} for l in d["lines"]]}), f"{d['number']}.pdf"

    def invoice_ubl(self, user, invoice_id: int) -> tuple[bytes, str]:
        d = self._document(user, "invoice", invoice_id)
        try:
            return ubl_mod.build(d), f"{d['number']}.xml"
        except ValueError as e:
            raise ApiError(422, str(e))

    def credit_note_ubl(self, user, note_id: int) -> tuple[bytes, str]:
        d = self._document(user, "credit", note_id)
        try:
            return ubl_mod.build(d), f"{d['number']}.xml"
        except ValueError as e:
            raise ApiError(422, str(e))

    def webhook(self, payload: bytes, signature: str) -> bool:
        try:
            ev = self.stripe.verify_webhook(payload, signature, now=self.clock())
        except PaymentError as e:
            raise ApiError(400, str(e))
        if ev.get("type") == "checkout.session.completed":
            obj = ev["data"]["object"]
            if obj.get("payment_status") == "paid":
                iid = int(obj.get("client_reference_id") or obj.get("metadata", {}).get("invoice_id") or 0)
                inv = self.db.one("SELECT * FROM invoices WHERE id=?", (iid,))
                if inv and inv["status"] == "open" and inv["provider_ref"] == obj.get("id"):
                    self.db.x("UPDATE invoices SET status='paid', paid=?, payment_ref=? WHERE id=?", (self.clock(), obj.get("payment_intent"), iid))
                    self.db.event(inv["user_id"], "invoice_paid", str(iid))
                    return True
        return False

    # ------------------------------------------------------------------ credit notes (operator)
    def _next_number(self, prefix: str, ts: float) -> str:
        year = datetime.fromtimestamp(ts, timezone.utc).year
        with self.db.lock:
            self.db.x("INSERT INTO counters(name,value) VALUES(?,0) ON CONFLICT(name) DO NOTHING", (f"{prefix}-{year}",))
            self.db.x("UPDATE counters SET value=value+1 WHERE name=?", (f"{prefix}-{year}",))
            n = self.db.one("SELECT value FROM counters WHERE name=?", (f"{prefix}-{year}",))["value"]
        return f"{prefix}-{year}-{n:05d}"

    def admin_invoices(self, user, limit: int = 100) -> list[dict]:
        if not user["is_admin"]:
            raise ApiError(404, "not found")
        return [{"id": i["id"], "number": i["number"], "org": i["org_name"], "period": i["period"], "total_usd": i["amount_usd"], "credited_usd": i["credited_usd"], "status": i["status"]}
                for i in self.db.q("SELECT i.*, o.name org_name FROM invoices i JOIN orgs o ON o.id=i.org_id WHERE i.number IS NOT NULL ORDER BY i.id DESC LIMIT ?", (max(1, min(limit, 500)),))]

    def admin_credit_note(self, user, invoice_id: int, amount_usd: float, reason: str) -> dict:
        """Credit part or all of an invoice's subtotal. Tax is credited at the invoice's own rate. An unpaid invoice is reduced; a paid one
        gets a refund (through Stripe when the payment is known, otherwise marked refund_due for the operator to pay back by hand)."""
        if not user["is_admin"]:
            raise ApiError(404, "not found")
        inv = self.db.one("SELECT * FROM invoices WHERE id=? AND number IS NOT NULL", (invoice_id,))
        if not inv:
            raise ApiError(404, "invoice not found")
        reason = (reason or "").strip()
        if not 3 <= len(reason) <= 300:
            raise ApiError(400, "give a reason (3 to 300 characters)")
        if not isinstance(amount_usd, (int, float)) or isinstance(amount_usd, bool) or amount_usd <= 0:
            raise ApiError(400, "amount must be a positive number")
        sub_left = round((inv["subtotal_usd"] or 0) - sum(r["subtotal_usd"] for r in self.db.q("SELECT subtotal_usd FROM credit_notes WHERE invoice_id=?", (inv["id"],))), 6)
        if amount_usd > sub_left + 1e-9:
            raise ApiError(400, f"at most {sub_left:.4f} of the subtotal can still be credited")
        rate = inv["tax_rate"] or 0.0
        tax = round(amount_usd * rate / 100, 4)
        total = round(amount_usd + tax, 4)
        number = self._next_number("CN", self.clock())
        status = "applied"
        ref = None
        if inv["status"] == "paid":
            status = "refund_due"
            if self.stripe.configured and inv["payment_ref"]:
                try:
                    ref = self.stripe.refund(inv["payment_ref"], total)
                    status = "refunded"
                except PaymentError:
                    status = "refund_due"                               # the credit note stands; the money still has to go back
        cid = self.db.x("INSERT INTO credit_notes(org_id,invoice_id,number,subtotal_usd,tax_usd,total_usd,reason,created,status,refund_ref,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (inv["org_id"], inv["id"], number, amount_usd, tax, total, reason, self.clock(), status, ref, user["id"]))
        credited = round(inv["credited_usd"] + total, 4)
        if inv["status"] == "open":
            remaining = round(inv["amount_usd"] - total, 4)
            self.db.x("UPDATE invoices SET amount_usd=?, credited_usd=?, status=? WHERE id=?", (max(0.0, remaining), credited, "credited" if remaining <= 1e-9 else "open", inv["id"]))
        else:
            self.db.x("UPDATE invoices SET credited_usd=? WHERE id=?", (credited, inv["id"]))
        self.db.event(user["id"], "credit_note", f"{number} {inv['number']} {total}")
        return {"id": cid, "number": number, "total_usd": total, "status": status, "refund_ref": ref}

    def credit_note_pdf(self, user, note_id: int) -> tuple[bytes, str]:
        d = self._document(user, "credit", note_id)
        cur = d["currency"].upper()
        return render_invoice({**d, "subtotal": -d["subtotal"], "tax": -d["tax"], "total": -d["total"],
                               "lines": [{"description": l["description"], "qty": "1", "unit": f"{-l['unit_price']:.2f} {cur}", "amount": -l["amount"]} for l in d["lines"]]}), f"{d['number']}.pdf"

    # ------------------------------------------------------------------ account tokens (console API) and sessions
    def create_token(self, user, name: str, scope: str = "read", ttl_days: int = 90) -> dict:
        """Personal access token for the console API (`Authorization: Bearer spt_...`). Shown once; only a hash is kept.
        scope "read" = GET only, "write" = everything the signed-in user can do except changing the password or deleting the account."""
        name = (name or "").strip()
        if not 1 <= len(name) <= 60:
            raise ApiError(400, "token name must be 1 to 60 characters")
        if scope not in ("read", "write"):
            raise ApiError(400, "scope must be read or write")
        if not isinstance(ttl_days, int) or not 1 <= ttl_days <= 365:
            raise ApiError(400, "lifetime must be 1 to 365 days")
        if self.db.one("SELECT COUNT(*) c FROM tokens WHERE user_id=? AND revoked IS NULL", (user["id"],))["c"] >= 20:
            raise ApiError(400, "limit of 20 active tokens reached")
        raw = "spt_" + sec.new_token()
        now = self.clock()
        tid = self.db.x("INSERT INTO tokens(user_id,name,token_hash,hint,scope,created,expires) VALUES(?,?,?,?,?,?,?)",
                        (user["id"], name, sec.token_hash(raw), raw[-4:], scope, now, now + ttl_days * 86400))
        self.db.event(user["id"], "token_created", f"{tid} {scope}")
        return {**self._token_view(self.db.one("SELECT * FROM tokens WHERE id=?", (tid,))), "token": raw, "shown_once": True}

    @staticmethod
    def _token_view(t) -> dict:
        return {"id": t["id"], "name": t["name"], "scope": t["scope"], "hint": t["hint"], "created": t["created"], "expires": t["expires"],
                "last_used": t["last_used"], "revoked": t["revoked"] is not None}

    def list_tokens(self, user) -> list[dict]:
        return [self._token_view(t) for t in self.db.q("SELECT * FROM tokens WHERE user_id=? ORDER BY id DESC", (user["id"],))]

    def revoke_token(self, user, token_id: int) -> None:
        t = self.db.one("SELECT * FROM tokens WHERE id=? AND user_id=?", (token_id, user["id"]))
        if not t:
            raise ApiError(404, "token not found")
        self.db.x("UPDATE tokens SET revoked=? WHERE id=? AND revoked IS NULL", (self.clock(), token_id))
        self.db.event(user["id"], "token_revoked", str(token_id))

    def bearer(self, raw: str | None):
        """(user row, scope) for a valid personal access token, else None."""
        if not raw or not raw.startswith("spt_"):
            return None
        t = self.db.one("SELECT * FROM tokens WHERE token_hash=?", (sec.token_hash(raw),))
        if not t or t["revoked"] is not None or t["expires"] < self.clock():
            return None
        u = self.db.one("SELECT * FROM users WHERE id=?", (t["user_id"],))
        if u:
            self.db.x("UPDATE tokens SET last_used=? WHERE id=?", (self.clock(), t["id"]))
        return (u, t["scope"]) if u else None

    def list_sessions(self, user, current_token: str | None) -> list[dict]:
        cur = sec.token_hash(current_token) if current_token else ""
        return [{"id": r["token_hash"][:12], "created": r["created"], "expires": r["expires"], "ip": r["ip"], "agent": (r["ua"] or "")[:80], "current": r["token_hash"] == cur}
                for r in self.db.q("SELECT * FROM sessions WHERE user_id=? AND expires>? ORDER BY created DESC", (user["id"], self.clock()))]

    def revoke_session(self, user, sid: str) -> None:
        if len(sid) != 12:
            raise ApiError(404, "session not found")
        self.db.x("DELETE FROM sessions WHERE user_id=? AND substr(token_hash,1,12)=?", (user["id"], sid))

    def activity(self, user, limit: int = 50) -> list[dict]:
        return [{"ts": e["ts"], "kind": e["kind"], "detail": e["detail"]} for e in
                self.db.q("SELECT ts,kind,detail FROM events WHERE user_id=? ORDER BY id DESC LIMIT ?", (user["id"], max(1, min(limit, 200))))]

    def update_profile(self, user, name: str) -> dict:
        name = (name or "").strip()
        if not 1 <= len(name) <= 80:
            raise ApiError(400, "enter your name (up to 80 characters)")
        self.db.x("UPDATE users SET name=? WHERE id=?", (name, user["id"]))
        return self.user_view(self.db.one("SELECT * FROM users WHERE id=?", (user["id"],)))

    def export_data(self, user) -> dict:
        """Everything the service holds about the user, as JSON (no secrets: password hash, token hashes, 2FA secret and key secrets are not included)."""
        orgs = self.list_orgs(user)
        oids = [o["id"] for o in orgs]
        qo = ",".join("?" * len(oids)) or "NULL"
        apps = [dict(a) for a in self.db.q(f"SELECT id,org_id,name,description,budget_usd,created,deleted FROM apps WHERE org_id IN ({qo})", oids)]
        ids = [a["id"] for a in apps]
        q = ",".join("?" * len(ids)) or "NULL"
        return {"account": self.user_view(user), "organizations": orgs, "apps": apps,
                "api_keys": [self.key_view(k) | {"app_id": k["app_id"]} for k in self.db.q(f"SELECT * FROM api_keys WHERE app_id IN ({q})", ids)],
                "tokens": self.list_tokens(user),
                "invoices": [dict(i) for i in self.db.q(f"SELECT id,org_id,number,period,amount_usd,status,created,paid FROM invoices WHERE org_id IN ({qo})", oids)],
                "usage_rows": self.db.one(f"SELECT COUNT(*) c FROM usage WHERE app_id IN ({q})", ids)["c"], "activity": self.activity(user, 200)}

    def delete_account(self, user, password: str) -> None:
        if not sec.verify_password(password or "", user["pw_hash"]):
            raise ApiError(403, "password is wrong")
        mine = self.db.q("SELECT m.org_id, m.role, o.personal FROM members m JOIN orgs o ON o.id=m.org_id WHERE m.user_id=?", (user["id"],))
        for m in mine:
            if m["personal"] or m["role"] != "owner":
                continue
            others = self.db.one("SELECT COUNT(*) c FROM members WHERE org_id=? AND user_id<>?", (m["org_id"], user["id"]))["c"]
            owners = self.db.one("SELECT COUNT(*) c FROM members WHERE org_id=? AND role='owner' AND user_id<>?", (m["org_id"], user["id"]))["c"]
            if others and not owners:
                raise ApiError(409, "you are the only owner of an organization with other members: make someone else owner or delete it first")
        for m in mine:                                                       # everything that would be orphaned goes; shared organizations stay
            alone = self.db.one("SELECT COUNT(*) c FROM members WHERE org_id=? AND user_id<>?", (m["org_id"], user["id"]))["c"] == 0
            if m["personal"] or alone:
                self._drop_org(m["org_id"], user)                            # raises if an invoice is open
            else:
                self.db.x("DELETE FROM members WHERE org_id=? AND user_id=?", (m["org_id"], user["id"]))
        with self.db.lock:
            for t in ("sessions", "tokens", "resets", "verifications", "challenges"):
                self.db.x(f"DELETE FROM {t} WHERE user_id=?", (user["id"],))
            self.db.x("DELETE FROM events WHERE user_id=?", (user["id"],))
            self.db.x("DELETE FROM users WHERE id=?", (user["id"],))

    # ------------------------------------------------------------------ the hub as seen by the console
    def _hub(self, cred_name: str, scopes: list[str], ttl_s: float = 120):
        from ..core.protocol import RpcClient
        if not (self.auth and self.hub_addr):
            raise ApiError(503, "this server is not connected to a hub")
        host, _, port = self.hub_addr.rpartition(":")
        try:
            return RpcClient(host or "127.0.0.1", int(port), self.auth.issue(cred_name, scopes, ttl_s=ttl_s).encode(), timeout=8)
        except (OSError, ConnectionError, RuntimeError) as e:
            raise ApiError(502, f"hub unreachable: {e}")

    def fleet(self, user) -> dict:
        """Nodes that joined with this user's node keys and the user's live tasks, read from the hub."""
        c = self._c(user)
        apps = {a["id"]: a for a in self.db.q("SELECT * FROM apps WHERE org_id=? AND deleted IS NULL", (c.org_id,))
                if c["app_scope"] is None or a["id"] in c["app_scope"]}
        tenants = [f"app{i}" for i in apps]
        out = {"hub": self.hub_public, "reachable": False, "nodes": [], "queue": {"counts": {}, "recent": []}}
        if not (self.auth and self.hub_addr):
            return out
        try:
            c = self._hub("platform:svc", ["fleet:read"])
            nodes = c.call({"op": "nodes", "window_s": 60})[0]["nodes"]
            q = c.call({"op": "queue", "recent": 30, "tenants": tenants})[0]
            c.close()
        except (ApiError, OSError, ConnectionError, RuntimeError):
            return out
        mine = []
        for n in nodes:
            tenant = n["node"].split(":", 1)[0]
            if tenant in tenants:
                mine.append({"node": n["node"], "app": apps[int(tenant[3:])]["name"], "app_id": int(tenant[3:]), "alive": n["alive"], "cores": n["cores"],
                             "cpu_percent": n["cpu_avg"], "ram_free_percent": n["ram_avail_pct"], "gpus": n["gpu_count"], "samples": n["samples"]})
        names = {f"app{i}": a["name"] for i, a in apps.items()}
        for t in q.get("recent", []):
            t["app"] = names.get(t.get("tenant"), t.get("tenant"))
        out.update(reachable=True, nodes=mine, queue=q)
        return out

    def workloads(self) -> list[dict]:
        """What a user may submit: a curated catalogue of the hub's allow-listed workloads, each with parameter names,
        suggested defaults and hard upper bounds (a job cannot be asked to run for hours on a shared fleet)."""
        from ..compute import workloads as W
        return [{"name": n, "title": c["title"], "doc": c["doc"], "params": [{"name": k, "default": d, "min": lo, "max": hi, "required": True} for k, (d, lo, hi) in c["params"].items()]}
                for n, c in CATALOG.items() if n in W.REGISTRY]

    def submit_job(self, user, app_id: int, workload: str, params: dict) -> dict:
        c = self._c(user)
        self._need(c, "jobs.submit")
        self._need_verified(c)
        a = self._app(c, app_id)
        if self.app_view(a)["over_budget"]:
            raise ApiError(402, "this app reached its monthly budget")
        wl = {w["name"]: w for w in self.workloads()}
        if workload not in wl:
            raise ApiError(400, "unknown workload")
        if not isinstance(params, dict) or len(json.dumps(params)) > 2000:
            raise ApiError(400, "params must be a small JSON object")
        spec = {p["name"]: p for p in wl[workload]["params"]}
        for k in params:
            if k not in spec:
                raise ApiError(400, f"unknown parameter '{k}' for {workload}")
        clean = {}
        for k, p in spec.items():
            v = params.get(k, p["default"])
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
                raise ApiError(400, f"parameter '{k}' must be a number")
            if not p["min"] <= v <= p["max"]:
                raise ApiError(400, f"parameter '{k}' must be between {p['min']} and {p['max']}")
            clean[k] = int(v) if isinstance(p["default"], int) and float(v).is_integer() else v
        params = clean
        c = self._hub(f"app{a['id']}:console", KEY_KINDS["client"])
        try:
            tid = c.call({"op": "submit", "workload": workload, "params": params})[0]["task_id"]
        except RuntimeError as e:
            raise ApiError(400, str(e))
        finally:
            c.close()
        self.db.event(user["id"], "job_submitted", f"{a['id']}/{tid} {workload}")
        return {"task_id": tid, "app_id": a["id"], "state": "queued"}

    def job_status(self, user, app_id: int, task_id: int) -> dict:
        a = self._app(user, app_id)
        c = self._hub("platform:svc", ["fleet:read", "fleet:submit"])
        try:
            t = c.call({"op": "task", "task_id": int(task_id)})[0]["task"]
        except RuntimeError:
            raise ApiError(404, "task not found (it may be older than the hub keeps)")
        finally:
            c.close()
        if t.get("tenant") != f"app{a['id']}":
            raise ApiError(404, "task not found")
        return {k: t.get(k) for k in ("id", "workload", "state", "node", "result", "error", "wall_s")}

    # ------------------------------------------------------------------ admin
    def admin_overview(self, user) -> dict:
        if not user["is_admin"]:
            raise ApiError(404, "not found")
        self.ingest_usage()
        cur = period_of(self.clock())
        a, b = period_bounds(cur)
        one = lambda sql, args=(): self.db.one(sql, args)["c"]
        out = {"users": one("SELECT COUNT(*) c FROM users"), "apps": one("SELECT COUNT(*) c FROM apps WHERE deleted IS NULL"),
               "active_keys": one("SELECT COUNT(*) c FROM api_keys WHERE revoked IS NULL AND expires>?", (self.clock(),)),
               "tasks_this_month": one("SELECT COUNT(*) c FROM usage WHERE ts>=? AND ts<?", (a, b)),
               "compute_hours_this_month": self.db.one("SELECT COALESCE(SUM(seconds),0) c FROM usage WHERE ts>=? AND ts<?", (a, b))["c"] / 3600,
               "open_invoices_usd": self.db.one("SELECT COALESCE(SUM(amount_usd),0) c FROM invoices WHERE status='open'")["c"],
               "unsent_mails": one("SELECT COUNT(*) c FROM outbox WHERE sent IS NULL"), "period": cur, "payments_enabled": self.stripe.configured,
               "smtp_configured": bool(self.smtp), "pricing_is_default": self.pricing_is_default, "hub": {"address": self.hub_public, "reachable": False}}
        if self.auth and self.hub_addr:
            try:
                c = self._hub("platform:svc", ["fleet:read"])
                n = c.call({"op": "nodes", "window_s": 60})
                q = c.call({"op": "queue", "recent": 5})[0]
                role = c.call({"op": "role"})[0]
                c.close()
                out["hub"].update(reachable=True, role=role.get("role"), epoch=role.get("epoch"), nodes=len(n[0]["nodes"]), nodes_up=sum(1 for x in n[0]["nodes"] if x["alive"]),
                                  queue=q["counts"], recommendations=n[0].get("utilization"))
            except (ApiError, OSError, ConnectionError, RuntimeError):
                pass
        return out

    def admin_settings(self, user) -> dict:
        if not user["is_admin"]:
            raise ApiError(404, "not found")
        return {"pricing": self.pricing.data, "pricing_is_default": self.pricing_is_default, "company": self.company(),
                "email": {"smtp_configured": bool(self.smtp), "require_verified": self.require_verified,
                          "unsent": self.db.one("SELECT COUNT(*) c FROM outbox WHERE sent IS NULL")["c"]},
                "payments_enabled": self.stripe.configured, "warnings": self._warnings()}

    def _warnings(self) -> list[str]:
        co, p, w = self.company(), self.pricing.data, []
        taxed = p["tax_rate_percent"] > 0 or any(v > 0 for v in p["tax_by_country"].values())
        if not co["name"] or not co["address"]:
            w.append("Company name and address are empty: they are printed on every invoice.")
        if taxed and not co["vat_id"]:
            w.append("Tax is charged but your company VAT id is empty: invoices with tax normally must show it.")
        if co["vat_id"] and not vat_mod.check(co["vat_id"])["ok"]:
            w.append("Your company VAT id does not look valid: " + vat_mod.check(co["vat_id"])["reason"])
        if taxed and not co["country"]:
            w.append("Set your company country: it decides when the simplified reverse charge applies.")
        if co["country"]:
            miss = [rules.COMPANY_FIELDS.get(f, f) for f in rules.required(co, taxed) if f not in ("name", "address", "vat_id") or (f == "vat_id" and not taxed and False)]
            miss = [m for m in miss if m not in ("company name", "address")]
            if miss:
                w.append(f"Invoices from {co['country']} normally need: " + ", ".join(miss) + ". This list is a checklist, not legal advice.")
        if self.pricing_is_default:
            w.append("You are using the example price list.")
        return w

    def admin_set_pricing(self, user, data: dict) -> dict:
        if not user["is_admin"]:
            raise ApiError(404, "not found")
        try:
            clean = validate_pricing(data if isinstance(data, dict) else {})
        except ValueError as e:
            raise ApiError(400, str(e))
        clean["note"] = (clean.get("note") or "").strip() if data.get("note") else "Set by the operator."
        self._set_setting("pricing", clean)
        self.db.event(user["id"], "pricing_changed", json.dumps({k: clean[k] for k in ("compute_usd_per_hour", "free_compute_hours_per_month", "tax_rate_percent")}))
        return self.admin_settings(user)

    COMPANY_TEXT = ("name", "address", "city", "postal_code", "vat_id", "email", "registration_no", "legal_form", "share_capital", "tax_no", "iban", "bic", "legal_footer", "tax_exempt_note")

    def admin_set_company(self, user, data: dict) -> dict:
        if not user["is_admin"]:
            raise ApiError(404, "not found")
        lim = {"address": 400, "legal_footer": 400, "tax_exempt_note": 200}
        f = {k: str(data.get(k) or "").strip()[:lim.get(k, 120)] for k in self.COMPANY_TEXT}
        f["country"] = str(data.get("country") or "").strip().upper()[:2]
        if f["country"] and not f["country"].isalpha():
            raise ApiError(400, "country must be a 2-letter code")
        if f["email"] and not sec.valid_email(f["email"]):
            raise ApiError(400, "enter a valid contact e-mail address")
        iban = re.sub(r"\s", "", f["iban"]).upper()
        if iban and not (re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban) and int("".join(str(int(ch, 36)) for ch in iban[4:] + iban[:4])) % 97 == 1):
            raise ApiError(400, "this IBAN is not valid (check the characters and the check digits)")
        f["iban"] = iban
        try:
            f["payment_terms_days"] = int(data.get("payment_terms_days", 30))
        except (TypeError, ValueError):
            raise ApiError(400, "payment terms must be a number of days")
        if not 0 <= f["payment_terms_days"] <= 120:
            raise ApiError(400, "payment terms must be between 0 and 120 days")
        self._set_setting("company", f)
        self.db.event(user["id"], "company_changed")
        return self.admin_settings(user)

    def admin_test_mail(self, user, to: str) -> dict:
        if not user["is_admin"]:
            raise ApiError(404, "not found")
        if not sec.valid_email(to or ""):
            raise ApiError(400, "enter a valid e-mail address")
        if not self.smtp:
            raise ApiError(503, "SMTP is not configured on this server (see --smtp-host)")
        mid = self.mailer.queue(to, "Spatial Computing test message", "If you can read this, e-mail delivery works.")
        r = self.db.one("SELECT sent, attempts, last_error FROM outbox WHERE id=?", (mid,))
        return {"sent": r["sent"] is not None, "error": r["last_error"]}

    def admin_mail(self, user, limit: int = 30) -> list[dict]:
        if not user["is_admin"]:
            raise ApiError(404, "not found")
        return [{"id": m["id"], "to": m["to_addr"], "subject": m["subject"], "created": m["created"], "sent": m["sent"], "attempts": m["attempts"], "error": m["last_error"]}
                for m in self.db.q("SELECT * FROM outbox ORDER BY id DESC LIMIT ?", (max(1, min(limit, 200)),))]

    def admin_users(self, user) -> list[dict]:
        if not user["is_admin"]:
            raise ApiError(404, "not found")
        cur = period_of(self.clock())
        a, b = period_bounds(cur)
        rows = []
        for u in self.db.q("SELECT * FROM users ORDER BY id"):
            sec_ = self.db.one("SELECT COALESCE(SUM(seconds),0) s FROM usage x JOIN apps p ON p.id=x.app_id WHERE p.user_id=? AND x.ts>=? AND x.ts<?", (u["id"], a, b))["s"]      # apps this user created
            rows.append({"id": u["id"], "email": u["email"], "name": u["name"], "is_admin": bool(u["is_admin"]), "created": u["created"],
                         "apps": self.db.one("SELECT COUNT(*) c FROM apps WHERE user_id=? AND deleted IS NULL", (u["id"],))["c"], "compute_hours_this_month": sec_ / 3600,
                         "locked": u["locked_until"] > self.clock()})
        return rows

    # ------------------------------------------------------------------ overview and test job
    def overview(self, user) -> dict:
        self.ingest_usage()
        apps = self.list_apps(user)
        cur = period_of(self.clock())
        secs = self._seconds_by_app(user, cur)
        a, b = period_bounds(cur)
        oc = self._c(user)
        ids = [x["id"] for x in apps]
        qm = ",".join("?" * len(ids)) or "NULL"
        tasks = self.db.one(f"SELECT COUNT(*) c FROM usage WHERE app_id IN ({qm}) AND ts>=? AND ts<?", (*ids, a, b))["c"]
        keys = [k for x in apps for k in x["keys"] if not k["revoked"]]
        total_tasks = self.db.one(f"SELECT COUNT(*) c FROM usage WHERE app_id IN ({qm})", tuple(ids))["c"]
        fl = self.fleet(user) if (self.auth and self.hub_addr) else {"reachable": False, "nodes": []}
        checklist = [{"key": "app", "done": bool(apps), "title": "Create an app", "hint": "A project with its own keys, usage and budget."},
                     {"key": "key", "done": bool(keys), "title": "Create an API key", "hint": "A client key to send work, a node key to add a machine."},
                     {"key": "node", "done": any(n["alive"] for n in fl["nodes"]), "title": "Connect a machine", "hint": "Run spatial agent with a node key."},
                     {"key": "job", "done": total_tasks > 0, "title": "Run a job", "hint": "Submit work from the Jobs page or the CLI."}]
        return {"checklist": checklist, "nodes_up": sum(1 for n in fl["nodes"] if n["alive"]), "nodes_total": len(fl["nodes"]), "hub_reachable": fl["reachable"],
                "apps": len(apps), "keys": len(keys), "tasks_this_month": tasks,
                "compute_hours_this_month": sum(secs.values()) / 3600, "estimated_usd": self._rate_org(oc, cur)["total_usd"], "role": oc["role"],
                "period": cur, "hub": self.hub_public}

    def run_test_job(self, user, app_id: int) -> dict:
        """Submit a small real job to the hub with a short-lived credential of this app, wait for it, return the result."""
        c = self._c(user)
        self._need(c, "jobs.submit")
        self._need_verified(c)
        a = self._app(c, app_id)
        if self.app_view(a)["over_budget"]:
            raise ApiError(402, "this app reached its monthly budget")
        if not (self.auth and self.hub_addr):
            raise ApiError(503, "this server is not connected to a hub")
        from ..core.protocol import RpcClient
        host, _, port = self.hub_addr.rpartition(":")
        token = self.auth.issue(f"app{a['id']}:test", KEY_KINDS["client"], ttl_s=120)
        try:
            cli = RpcClient(host or "127.0.0.1", int(port), token.encode(), timeout=10)
            tid = cli.call({"op": "submit", "workload": "montecarlo_pi", "params": {"samples": 200000, "seed": int(self.clock()) % 1000}})[0]["task_id"]
            deadline = time.time() + 20
            while time.time() < deadline:
                t = cli.call({"op": "task", "task_id": tid})[0]["task"]
                if t["state"] in ("done", "failed"):
                    cli.close()
                    return {"task_id": tid, "state": t["state"], "node": t.get("node"), "result": t.get("result"), "wall_s": t.get("wall_s"), "error": t.get("error")}
                time.sleep(0.25)
            cli.close()
            return {"task_id": tid, "state": "queued", "note": "no node picked the job up within 20 s: is an agent connected to the hub?"}
        except (OSError, ConnectionError, RuntimeError) as e:
            raise ApiError(502, f"hub unreachable: {e}")

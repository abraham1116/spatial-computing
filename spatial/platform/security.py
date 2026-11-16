"""Passwords, sessions, CSRF tokens, rate limiting. Standard library only."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")
COMMON = {"password", "12345678", "123456789", "qwertyuiop", "iloveyou1", "password1", "azertyuiop", "11111111"}


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


DUMMY_HASH = hash_password("dummy-password-for-timing")          # verified when the account does not exist: same cost either way


def check_password_policy(pw: str, email: str = "") -> str | None:
    if len(pw) < 10:
        return "password must have at least 10 characters"
    if len(pw) > 200:
        return "password is too long"
    if pw.lower() in COMMON or (email and pw.lower() == email.lower()):
        return "password is too common"
    if len(set(pw)) < 5:
        return "password is too repetitive"
    return None


def valid_email(e: str) -> bool:
    return bool(EMAIL_RE.match(e))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


class RateLimiter:
    """At most `limit` events per `window_s` per key, in memory."""

    def __init__(self, limit: int, window_s: float, clock=time.time):
        self.limit, self.window, self.clock = limit, window_s, clock
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 20000:                       # bound memory
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window}
            return True

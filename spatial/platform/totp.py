"""Time-based one-time passwords (RFC 6238, SHA-1, 6 digits, 30 s) and recovery codes. Standard library only."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

STEP = 30


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret: str, step: int, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    n = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 10 ** digits
    return str(n).zfill(digits)


def verify(secret: str, code: str, last_step: int = 0, now: float | None = None, window: int = 1) -> int | None:
    """Return the time step that matched, or None. A step at or before `last_step` is refused (a code works once)."""
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return None
    cur = int((now if now is not None else time.time()) // STEP)
    for s in range(cur - window, cur + window + 1):
        if s > last_step and hmac.compare_digest(code_at(secret, s), code):
            return s
    return None


def uri(secret: str, email: str, issuer: str = "Spatial Computing") -> str:
    return f"otpauth://totp/{urllib.parse.quote(issuer)}:{urllib.parse.quote(email)}?secret={secret}&issuer={urllib.parse.quote(issuer)}&algorithm=SHA1&digits=6&period={STEP}"


def new_recovery_codes(n: int = 8) -> list[str]:
    return [secrets.token_hex(5) for _ in range(n)]


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()

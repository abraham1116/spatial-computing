"""Scoped credentials, quotas and an audit trail for SWP/2 services.

A server started with a master key issues credentials to tenants. A credential names the
tenant, the scopes it may use, an expiry and optional quotas; it is signed with the master
key, so the server needs no database. The tenant's per-credential secret is
HMAC(master, credential): only the issuer can derive it, and it is what authenticates the
handshake. The token handed to a tenant is  "<credential>~<secret hex>".

Scopes are strings such as "run:mandel_numba", "mem:read", "mem:write", "exec:elf"; a trailing
"*" matches a prefix ("run:*", "*"). Services call require(scope) before acting.
Every request (allowed or denied) is appended to a hash-chained audit ledger.

Limits: revocation and usage counters live in the server process (restart resets counters);
a stolen token works until it expires or is revoked.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
from dataclasses import dataclass, field

from .ledger import Ledger

PREFIX = "spc1"


class QuotaExceeded(Exception):
    pass


class AuthError(Exception):
    pass


@dataclass
class Principal:
    name: str
    scopes: tuple[str, ...]
    expires: float
    max_ops: int | None = None
    max_bytes: int | None = None
    cred: str = ""
    ops: int = 0
    nbytes: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allows(self, scope: str) -> bool:
        for s in self.scopes:
            if s == "*" or s == scope or (s.endswith("*") and scope.startswith(s[:-1])):
                return True
        return False


_ctx = threading.local()


def current() -> Principal | None:
    return getattr(_ctx, "principal", None)


def set_current(p: Principal | None) -> None:
    _ctx.principal = p


def require(scope: str) -> None:
    """Raise PermissionError unless the calling tenant holds `scope` (always true without auth)."""
    p = current()
    if p is not None and not p.allows(scope):
        raise PermissionError(f"scope '{scope}' not granted to '{p.name}'")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class Authorizer:
    def __init__(self, master_key: bytes, audit: Ledger | None = None):
        if len(master_key) < 16:
            raise ValueError("master key must be at least 16 bytes")
        self._master = master_key
        self.audit = audit
        self._revoked: set[str] = set()
        self._seen: dict[str, Principal] = {}

    def _sig(self, payload: str) -> str:
        return hmac.new(self._master, b"sig|" + payload.encode(), hashlib.sha256).hexdigest()[:32]

    def secret_for(self, cred: str) -> bytes:
        return hmac.new(self._master, b"secret|" + cred.encode(), hashlib.sha256).digest()

    def issue(self, name: str, scopes: list[str], ttl_s: float = 3600, max_ops: int | None = None,
              max_bytes: int | None = None) -> str:
        body = {"n": name, "s": list(scopes), "e": time.time() + ttl_s}
        if max_ops is not None:
            body["o"] = max_ops
        if max_bytes is not None:
            body["b"] = max_bytes
        payload = _b64(json.dumps(body, separators=(",", ":")).encode())
        cred = f"{PREFIX}.{payload}.{self._sig(payload)}"
        return f"{cred}~{self.secret_for(cred).hex()}"

    def revoke(self, name: str) -> None:
        self._revoked.add(name)

    def principal(self, cred: str) -> Principal:
        """Verify signature, expiry and revocation. Raises AuthError."""
        try:
            prefix, payload, sig = cred.split(".")
        except ValueError:
            raise AuthError("malformed credential")
        if prefix != PREFIX or not hmac.compare_digest(sig, self._sig(payload)):
            raise AuthError("bad credential signature")
        body = json.loads(_unb64(payload))
        if body["e"] < time.time():
            raise AuthError("credential expired")
        if body["n"] in self._revoked:
            raise AuthError("credential revoked")
        if cred not in self._seen:
            self._seen[cred] = Principal(body["n"], tuple(body["s"]), body["e"], body.get("o"), body.get("b"), cred)
        return self._seen[cred]

    def charge(self, p: Principal, nbytes: int) -> None:
        with p.lock:
            if p.max_ops is not None and p.ops + 1 > p.max_ops:
                raise QuotaExceeded(f"'{p.name}' exceeded {p.max_ops} operations")
            if p.max_bytes is not None and p.nbytes + nbytes > p.max_bytes:
                raise QuotaExceeded(f"'{p.name}' exceeded {p.max_bytes} bytes")
            p.ops += 1
            p.nbytes += nbytes

    def log(self, p: Principal | None, op: str, ok: bool, detail: str = "", nbytes: int = 0) -> None:
        if self.audit is not None:
            self.audit.decide("auth", f"{p.name if p else '?'}:{op}", "allowed" if ok else f"denied: {detail}",
                              ok=ok, bytes=nbytes)


def parse_token(token: bytes) -> tuple[bytes, bytes]:
    """(credential, secret) from a client token. A plain shared token has no credential."""
    t = token.decode(errors="ignore") if token.startswith(PREFIX.encode() + b".") else ""
    if t and "~" in t:
        cred, secret_hex = t.split("~", 1)
        return cred.encode(), bytes.fromhex(secret_hex.strip())
    return b"", token


def init_master_key(path) -> None:
    """Create a random 32-byte master key file (mode 600). Refuses to overwrite."""
    import os
    from pathlib import Path
    p = Path(path)
    if p.exists():
        raise FileExistsError(f"{p} already exists; refusing to overwrite a master key")
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(os.urandom(32))


def authorizer_from_file(master_key_file, audit_path=None) -> Authorizer:
    from pathlib import Path
    audit = Ledger(audit_path) if audit_path else Ledger(Path.home() / ".spatial" / "audit.jsonl")
    return Authorizer(Path(master_key_file).read_bytes(), audit)

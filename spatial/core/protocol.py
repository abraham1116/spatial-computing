"""SPATIAL wire protocol v2 (SWP/2): authenticated, encrypted, forward-secret RPC over TCP.

Handshake  server -> client : nonce_s (16) | server ephemeral X25519 public key (32)
           client -> server : u16 cred_len | credential | client ephemeral public key (32) | nonce_c (16)
                              | HMAC-SHA256(secret, "SWP2c" | nonce_s | pub_s | pub_c | nonce_c | credential) (32)
Secret     the shared token, or, with scoped credentials, HMAC(master, credential) (see auth.py)
Keys       HKDF-SHA256(ikm = X25519 shared secret | secret, salt = nonce_s | nonce_c)
           -> one AES-256-GCM key per direction
Record     u32 length | AES-GCM(ciphertext | tag), nonce = 4 zero bytes | u64 record counter
Plaintext  u32 header_len | u32 blob_len | header (JSON utf-8) | blob (raw bytes)

Properties: the secret never crosses the wire; every record is confidential and integrity-
protected; replayed, reordered or modified records fail authentication; the ephemeral keys
are discarded after the handshake, so recorded sessions stay unreadable even if the secret is
stolen later (FORWARD SECRECY). A party that holds the secret *during* a session can still
impersonate (the secret is the only identity). Use TLS/WireGuard when you need certificates.

Safety: servers bind to 127.0.0.1 unless allow_remote=True is passed explicitly.
No code is ever transferred except by the sandboxed runner: requests name allow-listed operations.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import socketserver
import struct
import threading
from typing import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import auth

_HDR = struct.Struct(">II")
_LEN = struct.Struct(">I")
MAX_FRAME = 256 * 1024 * 1024
_RAW = dict(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray(n)
    view = memoryview(buf)
    got = 0
    while got < n:
        r = sock.recv_into(view[got:], n - got)
        if r == 0:
            raise ConnectionError("peer closed")
        got += r
    return bytes(buf)


class SecureChannel:
    """Encrypted, ordered record channel over a connected socket."""

    def __init__(self, sock: socket.socket, ikm: bytes, nonce_s: bytes, nonce_c: bytes, is_server: bool):
        okm = HKDF(algorithm=hashes.SHA256(), length=64, salt=nonce_s + nonce_c, info=b"SWP/2 keys").derive(ikm)
        c2s, s2c = AESGCM(okm[:32]), AESGCM(okm[32:])
        self._tx, self._rx = (s2c, c2s) if is_server else (c2s, s2c)
        self._ntx = self._nrx = 0
        self.sock = sock

    def send(self, header: dict, blob: bytes = b"") -> None:
        h = json.dumps(header, separators=(",", ":")).encode()
        plain = _HDR.pack(len(h), len(blob)) + h + blob
        ct = self._tx.encrypt(b"\0\0\0\0" + struct.pack(">Q", self._ntx), plain, None)
        self._ntx += 1
        self.sock.sendall(_LEN.pack(len(ct)) + ct)

    def recv(self) -> tuple[dict, bytes]:
        (n,) = _LEN.unpack(_recv_exact(self.sock, _LEN.size))
        if n > MAX_FRAME + 64:
            raise ValueError("record too large")
        try:
            plain = self._rx.decrypt(b"\0\0\0\0" + struct.pack(">Q", self._nrx), _recv_exact(self.sock, n), None)
        except InvalidTag:
            raise ConnectionError("record failed authentication (tampered, replayed or wrong key)")
        self._nrx += 1
        hl, bl = _HDR.unpack(plain[:_HDR.size])
        if _HDR.size + hl + bl != len(plain):
            raise ValueError("malformed record")
        header = json.loads(plain[_HDR.size:_HDR.size + hl]) if hl else {}
        if not isinstance(header, dict):
            raise ValueError("header must be a JSON object")
        return header, plain[_HDR.size + hl:]


def _mac(secret: bytes, nonce_s: bytes, pub_s: bytes, pub_c: bytes, nonce_c: bytes, cred: bytes) -> bytes:
    return hmac.new(secret, b"SWP2c" + nonce_s + pub_s + pub_c + nonce_c + cred, hashlib.sha256).digest()


Handler = Callable[[dict, bytes], tuple[dict, bytes]]


class RpcServer:
    """Threaded RPC server. Loopback-only by default.

    token       : shared secret (every client is trusted with every scope), or None
    authorizer  : scoped credentials, quotas, audit (see auth.py); takes precedence over token
    """

    def __init__(self, handler: Handler, token: bytes | None = None, host: str = "127.0.0.1",
                 port: int = 0, allow_remote: bool = False, authorizer: "auth.Authorizer | None" = None,
                 handshake_timeout_s: float = 10.0, max_connections: int = 512):
        if host not in ("127.0.0.1", "localhost", "::1") and not allow_remote:
            raise PermissionError(
                "refusing to bind a non-loopback address without allow_remote=True "
                "(explicit user consent required to expose this machine)")
        if token is None and authorizer is None:
            raise ValueError("RpcServer needs a token or an authorizer")
        outer = self
        slots = threading.BoundedSemaphore(max_connections)       # one thread per connection: cap them

        class _H(socketserver.BaseRequestHandler):
            def handle(self):
                if not slots.acquire(blocking=False):
                    return                                        # over the cap: drop before any work
                try:
                    self._serve()
                finally:
                    slots.release()

            def _serve(self):
                s = self.request
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.settimeout(handshake_timeout_s)                 # a silent peer must not hold a thread forever
                eph = X25519PrivateKey.generate()
                pub_s = eph.public_key().public_bytes(**_RAW)
                nonce_s = os.urandom(16)
                try:
                    s.sendall(nonce_s + pub_s)
                    (cl,) = struct.unpack(">H", _recv_exact(s, 2))
                    cred = _recv_exact(s, cl)
                    pub_c, nonce_c, mac = _recv_exact(s, 32), _recv_exact(s, 16), _recv_exact(s, 32)
                except (ConnectionError, OSError):
                    return
                principal = None
                if authorizer is not None:
                    try:
                        principal = authorizer.principal(cred.decode())
                    except (auth.AuthError, ValueError, UnicodeDecodeError, KeyError):
                        return                                    # silent drop
                    secret = authorizer.secret_for(cred.decode())
                else:
                    if cred:
                        return
                    secret = token
                if not hmac.compare_digest(mac, _mac(secret, nonce_s, pub_s, pub_c, nonce_c, cred)):
                    return                                        # silent drop on bad auth
                shared = eph.exchange(X25519PublicKey.from_public_bytes(pub_c))
                ch = SecureChannel(s, shared + secret, nonce_s, nonce_c, is_server=True)
                s.settimeout(None)                                # authenticated peers may stay idle (agents poll)
                while True:
                    try:
                        header, blob = ch.recv()
                    except (ConnectionError, OSError, ValueError, struct.error):
                        return
                    op = str(header.get("op"))
                    try:
                        if principal is not None:
                            authorizer.charge(principal, len(blob))
                        auth.set_current(principal)
                        rh, rb = outer.handler(header, blob)
                        rh.setdefault("ok", True)
                        if authorizer is not None:
                            authorizer.log(principal, op, True, nbytes=len(blob))
                    except Exception as e:  # report, never crash the server
                        rh, rb = {"ok": False, "error": f"{type(e).__name__}: {e}"}, b""
                        if authorizer is not None:
                            authorizer.log(principal, op, False, f"{type(e).__name__}: {e}", len(blob))
                    finally:
                        auth.set_current(None)
                    ch.send(rh, rb)

        class _S(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True
            request_queue_size = 1024              # the default backlog of 5 refused simultaneous reconnects (found by the scale test)

        self.handler = handler
        self._srv = _S((host, port), _H)
        self.host, self.port = self._srv.server_address[:2]
        self._thread: threading.Thread | None = None

    def start(self) -> "RpcServer":
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._thread.start()
        return self

    def serve_forever(self) -> None:
        self._srv.serve_forever()

    def stop(self) -> None:
        self._srv.shutdown()
        self._srv.server_close()


class RpcClient:
    """token: the shared secret, or a scoped token string from Authorizer.issue()."""

    def __init__(self, host: str, port: int, token: bytes, timeout: float = 120.0):
        cred, secret = auth.parse_token(token)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        hello = _recv_exact(self.sock, 48)
        nonce_s, pub_s = hello[:16], hello[16:]
        eph = X25519PrivateKey.generate()
        pub_c, nonce_c = eph.public_key().public_bytes(**_RAW), os.urandom(16)
        self.sock.sendall(struct.pack(">H", len(cred)) + cred + pub_c + nonce_c
                          + _mac(secret, nonce_s, pub_s, pub_c, nonce_c, cred))
        shared = eph.exchange(X25519PublicKey.from_public_bytes(pub_s))
        self._ch = SecureChannel(self.sock, shared + secret, nonce_s, nonce_c, is_server=False)
        self._lock = threading.Lock()

    def call(self, header: dict, blob: bytes = b"") -> tuple[dict, bytes]:
        with self._lock:
            self._ch.send(header, blob)
            rh, rb = self._ch.recv()
        if not rh.get("ok", False):
            raise RuntimeError(rh.get("error", "remote error"))
        return rh, rb

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

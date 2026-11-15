"""SPATIAL wire protocol v1 (SWP/1): authenticated AND encrypted RPC over TCP.

Handshake  server -> client : nonce_s (16 bytes)
           client -> server : HMAC-SHA256(token, nonce_s) (32 bytes) | nonce_c (16 bytes)
Keys       HKDF-SHA256(token, salt = nonce_s | nonce_c) -> one AES-256-GCM key per direction
Record     u32 length | AES-GCM(ciphertext | tag), nonce = 4 zero bytes | u64 record counter
Plaintext  u32 header_len | u32 blob_len | header (JSON utf-8) | blob (raw bytes)

Properties: the token never crosses the wire; every record is confidential and
integrity-protected; a replayed, reordered or modified record fails authentication.
Not provided: forward secrecy (a stolen token decrypts recorded sessions) and peer
identity beyond "knows the token". Use TLS/WireGuard on top for stronger guarantees.

Safety: servers bind to 127.0.0.1 unless allow_remote=True is passed explicitly.
No code is ever transferred: requests name allow-listed operations.
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
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_HDR = struct.Struct(">II")
_LEN = struct.Struct(">I")
MAX_FRAME = 256 * 1024 * 1024


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

    def __init__(self, sock: socket.socket, token: bytes, nonce_s: bytes, nonce_c: bytes, is_server: bool):
        okm = HKDF(algorithm=hashes.SHA256(), length=64, salt=nonce_s + nonce_c, info=b"SWP/1 keys").derive(token)
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
        return header, plain[_HDR.size + hl:]


Handler = Callable[[dict, bytes], tuple[dict, bytes]]


class RpcServer:
    """Threaded RPC server. Loopback-only by default."""

    def __init__(self, handler: Handler, token: bytes, host: str = "127.0.0.1",
                 port: int = 0, allow_remote: bool = False):
        if host not in ("127.0.0.1", "localhost", "::1") and not allow_remote:
            raise PermissionError(
                "refusing to bind a non-loopback address without allow_remote=True "
                "(explicit user consent required to expose this machine)")
        outer = self

        class _H(socketserver.BaseRequestHandler):
            def handle(self):
                s = self.request
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                nonce_s = os.urandom(16)
                s.sendall(nonce_s)
                try:
                    hello = _recv_exact(s, 48)
                except ConnectionError:
                    return
                if not hmac.compare_digest(hello[:32], hmac.new(token, nonce_s, hashlib.sha256).digest()):
                    return  # silent drop on bad auth
                ch = SecureChannel(s, token, nonce_s, hello[32:], is_server=True)
                while True:
                    try:
                        header, blob = ch.recv()
                    except (ConnectionError, OSError, ValueError):
                        return
                    try:
                        rh, rb = outer.handler(header, blob)
                        rh.setdefault("ok", True)
                    except Exception as e:  # report, never crash the server
                        rh, rb = {"ok": False, "error": f"{type(e).__name__}: {e}"}, b""
                    ch.send(rh, rb)

        class _S(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

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
    def __init__(self, host: str, port: int, token: bytes, timeout: float = 120.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        nonce_s = _recv_exact(self.sock, 16)
        nonce_c = os.urandom(16)
        self.sock.sendall(hmac.new(token, nonce_s, hashlib.sha256).digest() + nonce_c)
        self._ch = SecureChannel(self.sock, token, nonce_s, nonce_c, is_server=False)
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

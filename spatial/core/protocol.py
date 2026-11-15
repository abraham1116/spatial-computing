"""SPATIAL wire protocol v0 (SWP/0).

Frame  = u32 header_len | u32 blob_len | header(JSON utf-8) | blob(raw bytes)
Auth   = server sends 16-byte nonce; client answers HMAC-SHA256(token, nonce).
Safety = servers bind to 127.0.0.1 unless allow_remote=True is passed explicitly.
         No code is ever transferred: requests name whitelisted operations.
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

_HDR = struct.Struct(">II")
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


def send_frame(sock: socket.socket, header: dict, blob: bytes = b"") -> None:
    h = json.dumps(header, separators=(",", ":")).encode()
    sock.sendall(_HDR.pack(len(h), len(blob)) + h + blob)


def recv_frame(sock: socket.socket) -> tuple[dict, bytes]:
    hl, bl = _HDR.unpack(_recv_exact(sock, _HDR.size))
    if hl > MAX_FRAME or bl > MAX_FRAME:
        raise ValueError("frame too large")
    header = json.loads(_recv_exact(sock, hl)) if hl else {}
    blob = _recv_exact(sock, bl) if bl else b""
    return header, blob


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
                nonce = os.urandom(16)
                s.sendall(nonce)
                try:
                    mac = _recv_exact(s, 32)
                except ConnectionError:
                    return
                if not hmac.compare_digest(mac, hmac.new(token, nonce, hashlib.sha256).digest()):
                    return  # silent drop on bad auth
                while True:
                    try:
                        header, blob = recv_frame(s)
                    except (ConnectionError, OSError):
                        return
                    try:
                        rh, rb = outer.handler(header, blob)
                        rh.setdefault("ok", True)
                    except Exception as e:  # report, never crash the server
                        rh, rb = {"ok": False, "error": f"{type(e).__name__}: {e}"}, b""
                    send_frame(s, rh, rb)

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
        nonce = _recv_exact(self.sock, 16)
        self.sock.sendall(hmac.new(token, nonce, hashlib.sha256).digest())
        self._lock = threading.Lock()

    def call(self, header: dict, blob: bytes = b"") -> tuple[dict, bytes]:
        with self._lock:
            send_frame(self.sock, header, blob)
            rh, rb = recv_frame(self.sock)
        if not rh.get("ok", False):
            raise RuntimeError(rh.get("error", "remote error"))
        return rh, rb

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

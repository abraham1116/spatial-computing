"""Remote page server: holds compressed pages in ITS OWN RAM, served over SWP/0.

Run:  python -m spatial.memory.pageserver --token-file <path> [--delay-ms X] [--mbps Y]

--delay-ms / --mbps EMULATE a network (added round-trip delay, bandwidth cap) because the
test bench has a single machine. Results obtained with them are labelled "emulated link":
they bound what a real LAN/WAN would do, they are not measurements of one.
"""
from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from ..core.protocol import RpcClient, RpcServer


class PageStore:
    def __init__(self, delay_ms: float = 0.0, mbps: float = 0.0, max_bytes: int = 4 << 30):
        self.pages: dict[int, bytes] = {}
        self.bytes = 0
        self.delay = delay_ms / 1000.0
        self.bps = mbps * 1e6 / 8
        self.max_bytes = max_bytes

    def _link(self, nbytes: int):
        d = self.delay + (nbytes / self.bps if self.bps else 0.0)
        if d > 0:
            time.sleep(d)

    def handle(self, h: dict, blob: bytes):
        op = h["op"]
        if op == "put":
            if self.bytes + len(blob) > self.max_bytes:
                raise MemoryError("page server quota exceeded")
            old = self.pages.get(h["key"])
            if old is not None:
                self.bytes -= len(old)
            self.pages[h["key"]] = blob
            self.bytes += len(blob)
            self._link(len(blob))
            return {}, b""
        if op == "get":
            b = self.pages[h["key"]]
            self._link(len(b))
            return {}, b
        if op == "get_many":
            bl = [self.pages.get(k) for k in h["keys"]]
            out = b"".join(b for b in bl if b is not None)
            self._link(len(out))
            return {"lens": [len(b) if b is not None else -1 for b in bl]}, out
        if op == "del":
            b = self.pages.pop(h["key"], None)
            if b is not None:
                self.bytes -= len(b)
            return {}, b""
        if op == "stat":
            return {"pages": len(self.pages), "bytes": self.bytes}, b""
        raise ValueError(op)


class LocalPageServer:
    """Page server in a separate OS process on loopback."""

    def __init__(self, delay_ms: float = 0.0, mbps: float = 0.0):
        self.token = secrets.token_bytes(32)
        self._tf = Path(os.environ.get("TMPDIR", "/tmp")) / f"spatial-ps-{os.getpid()}-{secrets.token_hex(4)}"
        self._tf.write_bytes(self.token)
        os.chmod(self._tf, 0o600)
        root = Path(__file__).resolve().parents[2]
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "spatial.memory.pageserver", "--token-file", str(self._tf),
             "--delay-ms", str(delay_ms), "--mbps", str(mbps)],
            cwd=root, stdout=subprocess.PIPE, text=True)
        line = self.proc.stdout.readline()
        if not line.startswith("PORT "):
            raise RuntimeError(f"page server failed: {line!r}")
        self.port = int(line.split()[1])

    def client(self) -> RpcClient:
        return RpcClient("127.0.0.1", self.port, self.token)

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self._tf.unlink(missing_ok=True)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--delay-ms", type=float, default=0.0)
    ap.add_argument("--mbps", type=float, default=0.0)
    ap.add_argument("--allow-remote", action="store_true")
    a = ap.parse_args()
    store = PageStore(a.delay_ms, a.mbps)
    srv = RpcServer(store.handle, Path(a.token_file).read_bytes(), a.host, a.port, a.allow_remote)
    print(f"PORT {srv.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

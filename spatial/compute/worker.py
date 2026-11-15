"""Compute worker: executes whitelisted workloads by name over SWP/0.

Run:  python -m spatial.compute.worker --token-file <path> [--port 0]
Binds 127.0.0.1 only. Exposing it on a LAN requires --allow-remote AND --host,
which is a deliberate, explicit act by the machine owner.
"""
from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from ..core.auth import authorizer_from_file, require
from ..core.protocol import RpcClient, RpcServer
from . import workloads


def _handler(header: dict, blob: bytes):
    op = header.get("op")
    if op == "ping":
        return {"pong": True, "pid": os.getpid()}, b""
    if op == "run":
        require(f"run:{header.get('workload')}")
        t = os.times()
        c0, w0 = t.user + t.system, time.perf_counter()
        result = workloads.run(header["workload"], **header.get("params", {}))
        t = os.times()
        return {"result": result, "wall_s": time.perf_counter() - w0,
                "cpu_s": t.user + t.system - c0}, b""
    raise ValueError(f"unknown op {op!r}")


def serve(token: bytes | None, host: str = "127.0.0.1", port: int = 0, allow_remote: bool = False,
          authorizer=None) -> RpcServer:
    return RpcServer(_handler, token, host=host, port=port, allow_remote=allow_remote, authorizer=authorizer)


class LocalWorkerProcess:
    """Spawns a worker as a separate OS process on loopback (stand-in for a second machine:
    it validates the protocol and its overhead, NOT the gain of extra hardware)."""

    def __init__(self):
        self.token = secrets.token_bytes(32)
        self._tf = Path(os.environ.get("TMPDIR", "/tmp")) / f"spatial-token-{os.getpid()}-{secrets.token_hex(4)}"
        self._tf.write_bytes(self.token)
        os.chmod(self._tf, 0o600)
        root = Path(__file__).resolve().parents[2]
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "spatial.compute.worker", "--token-file", str(self._tf)],
            cwd=root, stdout=subprocess.PIPE, text=True)
        line = self.proc.stdout.readline()
        if not line.startswith("PORT "):
            raise RuntimeError(f"worker failed to start: {line!r}")
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
    ap.add_argument("--token-file", help="shared secret (every client may do everything)")
    ap.add_argument("--master-key-file", help="issue scoped credentials instead (see `spatial token`)")
    ap.add_argument("--audit-log")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--allow-remote", action="store_true",
                    help="explicit consent to accept non-loopback connections")
    a = ap.parse_args()
    if bool(a.token_file) == bool(a.master_key_file):
        raise SystemExit("give exactly one of --token-file or --master-key-file")
    srv = serve(Path(a.token_file).read_bytes() if a.token_file else None, a.host, a.port, a.allow_remote,
                authorizer_from_file(a.master_key_file, a.audit_log) if a.master_key_file else None)
    print(f"PORT {srv.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

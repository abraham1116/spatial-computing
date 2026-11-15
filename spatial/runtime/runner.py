"""Remote execution: a runner that accepts a Linux ELF over SWP/1 and runs it ONLY inside a
micro-VM (no network, no disk, no host files, RAM capped). This is the one place where
code crosses the wire, which is why the sandbox is not optional and cannot be disabled
by the caller.

Run:  spatial serve runtime --token-file <path>
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

from ..core.protocol import RpcClient, RpcServer
from . import microvm
from .inspect import inspect

MAX_ELF = 64 * 1024 * 1024
MAX_TIMEOUT = 300.0


def _handler(h: dict, blob: bytes):
    op = h.get("op")
    if op == "ping":
        return {"pong": True, "microvm": microvm.available()}, b""
    if op != "run_elf":
        raise ValueError(f"unknown op {op!r}")
    if len(blob) > MAX_ELF:
        raise ValueError("binary too large")
    args = [str(a) for a in h.get("args", [])]
    if any(c in a for a in args for c in "\n;&|`$<>"):
        raise ValueError("argument contains shell metacharacters")
    with tempfile.NamedTemporaryFile(prefix="spatial-remote-", suffix=".elf", delete=False) as f:
        f.write(blob)
        path = f.name
    try:
        art = inspect(path)
        if art.format != "elf" or "x86_64" not in art.arch:
            raise ValueError(f"runner only accepts Linux x86_64 ELF binaries, got {art.format}/{art.arch}")
        accel = "hvf" if h.get("accel", "hvf") == "hvf" else "tcg"
        r = microvm.run_elf(path, args, accel=accel, mem_mb=min(int(h.get("mem_mb", 256)), 1024),
                            timeout_s=min(float(h.get("timeout_s", 120)), MAX_TIMEOUT))
    finally:
        os.unlink(path)
    return {"run_ok": r.ok, "exit_code": r.exit_code, "stdout": r.stdout, "boot_s": r.boot_s,
            "total_wall_s": r.total_wall_s, "accel": r.accel}, b""


def serve(token: bytes, host: str = "127.0.0.1", port: int = 0, allow_remote: bool = False) -> RpcServer:
    return RpcServer(_handler, token, host=host, port=port, allow_remote=allow_remote)


def run_remote(client: RpcClient, elf_path: str, args: list[str] | None = None, **opts) -> dict:
    rh, _ = client.call({"op": "run_elf", "args": args or [], **opts}, Path(elf_path).read_bytes())
    return rh


class LocalRunnerProcess:
    """Runner in a separate OS process on loopback (stand-in for a remote host)."""

    def __init__(self):
        self.token = secrets.token_bytes(32)
        self._tf = Path(os.environ.get("TMPDIR", "/tmp")) / f"spatial-rt-{os.getpid()}-{secrets.token_hex(4)}"
        self._tf.write_bytes(self.token)
        os.chmod(self._tf, 0o600)
        self.proc = subprocess.Popen([sys.executable, "-m", "spatial.runtime.runner", "--token-file", str(self._tf)],
                                     cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, text=True)
        line = self.proc.stdout.readline()
        if not line.startswith("PORT "):
            raise RuntimeError(f"runner failed to start: {line!r}")
        self.port = int(line.split()[1])

    def client(self) -> RpcClient:
        return RpcClient("127.0.0.1", self.port, self.token, timeout=MAX_TIMEOUT + 30)

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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--allow-remote", action="store_true")
    a = ap.parse_args()
    srv = serve(Path(a.token_file).read_bytes(), a.host, a.port, a.allow_remote)
    print(f"PORT {srv.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

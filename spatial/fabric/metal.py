"""Metal compute backend (macOS): compiles the bundled Swift program once, then runs it per job."""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path

SRC = Path(__file__).with_name("metal_mandel.swift")
CACHE = Path.home() / ".cache" / "spatial"
BIN = CACHE / "metal_mandel"


def available() -> bool:
    return platform.system() == "Darwin" and (BIN.exists() or shutil.which("swiftc") is not None)


def ensure_binary() -> Path:
    if BIN.exists() and BIN.stat().st_mtime >= SRC.stat().st_mtime:
        return BIN
    if platform.system() != "Darwin" or not shutil.which("swiftc"):
        raise RuntimeError("Metal backend needs macOS and swiftc")
    CACHE.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["swiftc", "-O", str(SRC), "-o", str(BIN)], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("swiftc failed: " + r.stderr[-300:])
    return BIN


def mandel(n: int, iters: int, reps: int = 1) -> dict:
    out = subprocess.run([str(ensure_binary()), str(n), str(iters), str(reps)], capture_output=True, text=True, timeout=600)
    try:
        d = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        raise RuntimeError("Metal program failed: " + (out.stdout + out.stderr)[-300:])
    if not d.get("ok"):
        raise RuntimeError(d.get("error", "Metal error"))
    return d


def device_name() -> str | None:
    try:
        return mandel(8, 8, 1)["device"]
    except Exception:
        return None


RUN_SRC = Path(__file__).with_name("metal_run.swift")
RUN_BIN = CACHE / "metal_run"


def _ensure_run_binary() -> Path:
    if RUN_BIN.exists() and RUN_BIN.stat().st_mtime >= RUN_SRC.stat().st_mtime:
        return RUN_BIN
    if platform.system() != "Darwin" or not shutil.which("swiftc"):
        raise RuntimeError("Metal backend needs macOS and swiftc")
    CACHE.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["swiftc", "-O", str(RUN_SRC), "-o", str(RUN_BIN)], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("swiftc failed: " + r.stderr[-300:])
    return RUN_BIN


def run_kernel(k, n: int, params: dict, reps: int = 1, timing: dict | None = None, reduce: bool = False):
    """Run a portable Kernel (spatial.kernel) on the Metal GPU; returns the (n, n) uint32 output, or with reduce=True the sum of all outputs (computed in threadgroup shared memory, partial sums added on the host).
    `timing`, if given, receives the GPU-side median seconds."""
    import numpy as np
    import tempfile
    binary = _ensure_run_binary()
    with tempfile.TemporaryDirectory() as d:
        msl, out = Path(d) / "k.metal", Path(d) / "out.bin"
        msl.write_text(k.to_metal(reduce=reduce))
        args = [str(binary), str(msl), k.name + ("_sum" if reduce else ""), str(n), str(reps), str(out), "sum" if reduce else "map"]
        args += [f"{t}:{float(params[p]) if t == 'float' else int(params[p])}" for p, t in k.params]
        r = subprocess.run(args, capture_output=True, text=True, timeout=600)
        try:
            info = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            raise RuntimeError("Metal program failed: " + (r.stdout + r.stderr)[-300:])
        if not info.get("ok"):
            raise RuntimeError(info.get("error", "Metal error"))
        if timing is not None:
            timing.update(info)
        if reduce:
            return int(np.fromfile(out, dtype=np.uint64).sum())
        return np.fromfile(out, dtype=np.uint32).reshape(n, n)

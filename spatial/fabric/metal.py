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

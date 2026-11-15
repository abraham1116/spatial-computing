"""Cross-compilation of one C source to several executable formats (zig cc from PyPI `ziglang`).
Used to produce REAL foreign binaries for the runtime tests instead of mock files."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TARGETS = {
    "macos-x86_64": (None, "bench-macos"),                       # host clang
    "linux-x86_64": ("x86_64-linux-musl", "bench-linux.elf"),
    "windows-x86_64": ("x86_64-windows-gnu", "bench-windows.exe"),
    "wasm32-wasi": ("wasm32-wasi", "bench.wasm"),
}
FLAGS = ["-O2", "-ffp-contract=off"]   # no FMA contraction: identical IEEE results everywhere


def build(src: str, out_dir: str, target: str) -> Path:
    triple, name = TARGETS[target]
    out = Path(out_dir) / name
    out.parent.mkdir(parents=True, exist_ok=True)
    if triple is None:
        cmd = ["clang", *FLAGS, src, "-o", str(out)]
    else:
        cmd = [sys.executable, "-m", "ziglang", "cc", "-target", triple, *FLAGS, src, "-o", str(out)]
        if "linux" in triple:
            cmd.insert(-2, "-static")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"build {target} failed: {r.stderr[-800:]}")
    return out


def build_all(src: str, out_dir: str) -> dict[str, Path]:
    return {t: build(src, out_dir, t) for t in TARGETS}

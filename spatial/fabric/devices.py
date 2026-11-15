"""Discover the compute devices this machine can offer to the planner."""
from __future__ import annotations

import platform
from dataclasses import dataclass

import psutil

from . import cuda, metal


@dataclass
class Device:
    id: str
    kind: str            # cpu | gpu
    vendor: str
    name: str
    backend: str         # numba | metal | cuda
    available: bool
    note: str = ""


def discover() -> list[Device]:
    from ..compute.detect import _nvidia_gpus
    out = [Device("cpu", "cpu", platform.processor() or platform.machine(), f"{psutil.cpu_count(logical=False)} cores", "numba", True)]
    if platform.system() == "Darwin":
        ok = metal.available()
        out.append(Device("metal", "gpu", "Apple/Intel (Metal)", (metal.device_name() or "Metal GPU") if ok else "Metal GPU", "metal", ok,
                          "" if ok else "needs swiftc"))
    for i, g in enumerate(_nvidia_gpus()):
        out.append(Device(f"cuda:{i}", "gpu", "NVIDIA", g["name"], "cuda", cuda.available(),
                          "" if cuda.available() else "nvidia-smi sees it but numba.cuda does not: install numba CUDA support"))
    if not any(d.vendor == "NVIDIA" for d in out):
        out.append(Device("cuda", "gpu", "NVIDIA", "no NVIDIA GPU detected", "cuda", False, "no nvidia-smi"))
    return out

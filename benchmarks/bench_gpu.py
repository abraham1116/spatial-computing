"""TEST 3 — GPU: local GPU (Metal compute, Intel Iris Plus 640) vs CPU on the same job.

The GPU has no float64, so the comparison is done in float32 on both sides (a float32
Numba kernel is the CPU counterpart). CPU and GPU round differently (FMA contraction),
so checksums are compared by relative difference, not equality.
Remote GPU: none available/configured -> not tested (documented, not simulated).
"""
from __future__ import annotations

import json
import subprocess
import time

import numpy as np
from numba import njit, prange

from common import ROOT, save, timeit


@njit(cache=True, parallel=True)
def mandel_f32(n, iters):
    total = 0
    fn = np.float32(n)
    for i in prange(n):
        ci = np.float32(-1.3) + np.float32(2.6) * np.float32(i) / fn
        row = 0
        for j in range(n):
            cr = np.float32(-2.0) + np.float32(2.6) * np.float32(j) / fn
            zr = np.float32(0.0)
            zi = np.float32(0.0)
            k = 0
            while k < iters and zr * zr + zi * zi <= np.float32(4.0):
                t = zr * zr - zi * zi + cr
                zi = np.float32(2.0) * zr * zi + ci
                zr = t
                k += 1
            row += k
        total += row
    return total


def main():
    src = ROOT / "benchmarks/src/metal_mandel.swift"
    exe = ROOT / "benchmarks/build/metal_mandel"
    exe.parent.mkdir(exist_ok=True)
    out = {"rows": [], "remote_gpu": "not tested: no remote GPU host or cloud account configured"}
    t0 = time.perf_counter()
    r = subprocess.run(["swiftc", "-O", str(src), "-o", str(exe)], capture_output=True, text=True, timeout=600)
    out["swift_build_s"] = time.perf_counter() - t0
    if r.returncode != 0:
        out["error"] = "swiftc failed: " + r.stderr[-1500:]
        print(out["error"])
        save("gpu", out)
        return
    mandel_f32(16, 16)
    for n, iters in ((1024, 300), (2048, 300), (4096, 300), (2048, 2000)):
        g = subprocess.run([str(exe), str(n), str(iters)], capture_output=True, text=True, timeout=600)
        try:
            gj = json.loads(g.stdout.strip().splitlines()[-1])
        except Exception:
            gj = {"ok": False, "error": (g.stdout + g.stderr)[-500:]}
        t_cpu, _, chk = timeit(lambda: int(mandel_f32(n, iters)), 3)
        row = {"n": n, "iters": iters, "cpu_numba_threads_f32_s": t_cpu, "cpu_checksum": chk, "gpu": gj}
        if gj.get("ok"):
            row["gpu_s"] = gj["gpu_s_median"]
            row["gpu_speedup_vs_cpu"] = t_cpu / gj["gpu_s_median"]
            row["checksum_rel_diff"] = abs(gj["checksum"] - chk) / chk
        out["rows"].append(row)
        print({k: v for k, v in row.items() if k != "gpu"}, gj.get("device"), gj.get("error"))
    save("gpu", out)


if __name__ == "__main__":
    main()

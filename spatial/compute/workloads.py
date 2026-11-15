"""Whitelisted workloads. Every variant of a workload must return the same checksum,
so a faster strategy is only accepted if it computes the same thing."""
from __future__ import annotations

import hashlib
import os

import numpy as np

# workqueue: no TBB/OpenMP dependency, safe with subprocess use from helper threads
os.environ.setdefault("NUMBA_THREADING_LAYER", "workqueue")

try:
    import numba
    from numba import njit, prange
    HAVE_NUMBA = True
except Exception:  # pragma: no cover
    HAVE_NUMBA = False

# Mandelbrot window
X0, X1, Y0, Y1 = -2.0, 0.6, -1.3, 1.3


def mandel_python(n: int, iters: int, r0: int = 0, r1: int | None = None) -> int:
    r1 = n if r1 is None else r1
    total = 0
    for i in range(r0, r1):
        ci = Y0 + (Y1 - Y0) * i / n
        for j in range(n):
            cr = X0 + (X1 - X0) * j / n
            zr = zi = 0.0
            k = 0
            while k < iters and zr * zr + zi * zi <= 4.0:
                zr, zi = zr * zr - zi * zi + cr, 2.0 * zr * zi + ci
                k += 1
            total += k
    return total


def mandel_numpy(n: int, iters: int, r0: int = 0, r1: int | None = None) -> int:
    r1 = n if r1 is None else r1
    ci = (Y0 + (Y1 - Y0) * np.arange(r0, r1) / n)[:, None]
    cr = (X0 + (X1 - X0) * np.arange(n) / n)[None, :]
    c = cr + 1j * ci
    z = np.zeros_like(c)
    count = np.zeros(c.shape, dtype=np.int64)
    alive = np.ones(c.shape, dtype=bool)
    for _ in range(iters):
        alive &= (z.real * z.real + z.imag * z.imag) <= 4.0
        if not alive.any():
            break
        count[alive] += 1
        z[alive] = z[alive] * z[alive] + c[alive]
    return int(count.sum())


if HAVE_NUMBA:
    @njit(cache=True, fastmath=False, nogil=True)   # nogil: usable from threads
    def _mandel_nb(n, iters, r0, r1):
        total = 0
        for i in range(r0, r1):
            ci = Y0 + (Y1 - Y0) * i / n
            for j in range(n):
                cr = X0 + (X1 - X0) * j / n
                zr = 0.0
                zi = 0.0
                k = 0
                while k < iters and zr * zr + zi * zi <= 4.0:
                    t = zr * zr - zi * zi + cr
                    zi = 2.0 * zr * zi + ci
                    zr = t
                    k += 1
                total += k
        return total

    @njit(cache=True, parallel=True, fastmath=False)
    def _mandel_nb_par(n, iters, r0, r1):
        total = 0
        for i in prange(r0, r1):
            ci = Y0 + (Y1 - Y0) * i / n
            row = 0
            for j in range(n):
                cr = X0 + (X1 - X0) * j / n
                zr = 0.0
                zi = 0.0
                k = 0
                while k < iters and zr * zr + zi * zi <= 4.0:
                    t = zr * zr - zi * zi + cr
                    zi = 2.0 * zr * zi + ci
                    zr = t
                    k += 1
                row += k
            total += row
        return total


def mandel_numba(n: int, iters: int, r0: int = 0, r1: int | None = None) -> int:
    return int(_mandel_nb(n, iters, r0, n if r1 is None else r1))


def mandel_numba_parallel(n: int, iters: int, r0: int = 0, r1: int | None = None) -> int:
    return int(_mandel_nb_par(n, iters, r0, n if r1 is None else r1))


def montecarlo_pi(samples: int, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    inside = 0
    left = samples
    while left > 0:
        k = min(left, 2_000_000)
        xy = rng.random((k, 2))
        inside += int(((xy * xy).sum(axis=1) <= 1.0).sum())
        left -= k
    return 4.0 * inside / samples


def sha256_chain(rounds: int, size: int = 1 << 20) -> str:
    """Hash-bound workload (memory-bandwidth + SHA extensions if any)."""
    buf = bytes(size)
    h = hashlib.sha256()
    for _ in range(rounds):
        h.update(buf)
    return h.hexdigest()


def matmul(n: int, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    a = rng.random((n, n), dtype=np.float32)
    b = rng.random((n, n), dtype=np.float32)
    return float((a @ b).trace())


REGISTRY = {
    "mandel_python": mandel_python,
    "mandel_numpy": mandel_numpy,
    "montecarlo_pi": montecarlo_pi,
    "sha256_chain": sha256_chain,
    "matmul": matmul,
}
if HAVE_NUMBA:
    REGISTRY["mandel_numba"] = mandel_numba
    REGISTRY["mandel_numba_parallel"] = mandel_numba_parallel


def run(name: str, **params):
    if name not in REGISTRY:
        raise KeyError(f"workload '{name}' is not whitelisted")
    return REGISTRY[name](**params)

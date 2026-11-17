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

    @njit(cache=True, parallel=True)
    def _mandel_f32_cpu(n, iters):
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


def mandel_f32_cpu(n: int, iters: int) -> int:
    """Fabric: float32 Mandelbrot on the CPU (Numba, all cores). Same job as the GPU variants."""
    return int(_mandel_f32_cpu(n, iters))


def mandel_f32_metal(n: int, iters: int) -> int:
    """Fabric: the same job on a Metal GPU (macOS)."""
    from ..fabric import metal
    return int(metal.mandel(n, iters, 1)["checksum"])


def mandel_f32_cuda(n: int, iters: int) -> int:
    """Fabric: the same job on an NVIDIA GPU. Never run on real NVIDIA hardware."""
    from ..fabric import cuda
    if not cuda.available():
        raise RuntimeError("no CUDA device visible to numba")
    return cuda.mandel(n, iters)


def _pk(name: str, device: str, n: int, **params) -> int:
    from ..kernel.library import LIBRARY
    return int(LIBRARY[name].run(device, n, **params).astype("uint64").sum())


def pk_mandel_cpu(n: int, iters: int) -> int:
    """Portable kernel (spatial.kernel) on the CPU: the SAME source as the Metal variant."""
    return _pk("mandelbrot", "cpu", n, iters=iters)


def pk_mandel_metal(n: int, iters: int) -> int:
    return _pk("mandelbrot", "metal", n, iters=iters)


def pk_collatz_cpu(n: int, limit: int) -> int:
    return _pk("collatz", "cpu", n, limit=limit)


def pk_collatz_metal(n: int, limit: int) -> int:
    return _pk("collatz", "metal", n, limit=limit)


def pk_batch_score_cpu(n: int, signals: int) -> int:
    """Portable kernel (spatial.kernel): a batch-scoring workload (fraud/risk/ranking-shaped), on the CPU."""
    return _pk("batch_score", "cpu", n, signals=signals)


def pk_batch_score_metal(n: int, signals: int) -> int:
    return _pk("batch_score", "metal", n, signals=signals)

def pk_rtb_cpu(n: int, signals: int) -> int:
    """Portable kernel (spatial.kernel): a real-time ad-bid score (RTB-shaped), on the CPU. SAME kernel as pk_batch_score (`batch_score`
    in spatial.kernel.library), only the name and docs differ: synthetic signals, no trained model,
    no real data for this vertical. See docs/KERNELS.md."""
    return _pk("batch_score", "cpu", n, signals=signals)


def pk_rtb_metal(n: int, signals: int) -> int:
    return _pk("batch_score", "metal", n, signals=signals)

def pk_credit_cpu(n: int, signals: int) -> int:
    """Portable kernel (spatial.kernel): a credit/loan application score, on the CPU. SAME kernel as pk_batch_score (`batch_score`
    in spatial.kernel.library), only the name and docs differ: synthetic signals, no trained model,
    no real data for this vertical. See docs/KERNELS.md."""
    return _pk("batch_score", "cpu", n, signals=signals)


def pk_credit_metal(n: int, signals: int) -> int:
    return _pk("batch_score", "metal", n, signals=signals)

def pk_claims_cpu(n: int, signals: int) -> int:
    """Portable kernel (spatial.kernel): an insurance claim score, on the CPU. SAME kernel as pk_batch_score (`batch_score`
    in spatial.kernel.library), only the name and docs differ: synthetic signals, no trained model,
    no real data for this vertical. See docs/KERNELS.md."""
    return _pk("batch_score", "cpu", n, signals=signals)


def pk_claims_metal(n: int, signals: int) -> int:
    return _pk("batch_score", "metal", n, signals=signals)

def pk_alerts_cpu(n: int, signals: int) -> int:
    """Portable kernel (spatial.kernel): a security alert score (SIEM-shaped), on the CPU. SAME kernel as pk_batch_score (`batch_score`
    in spatial.kernel.library), only the name and docs differ: synthetic signals, no trained model,
    no real data for this vertical. See docs/KERNELS.md."""
    return _pk("batch_score", "cpu", n, signals=signals)


def pk_alerts_metal(n: int, signals: int) -> int:
    return _pk("batch_score", "metal", n, signals=signals)

def pk_moderation_cpu(n: int, signals: int) -> int:
    """Portable kernel (spatial.kernel): a content moderation score, on the CPU. SAME kernel as pk_batch_score (`batch_score`
    in spatial.kernel.library), only the name and docs differ: synthetic signals, no trained model,
    no real data for this vertical. See docs/KERNELS.md."""
    return _pk("batch_score", "cpu", n, signals=signals)


def pk_moderation_metal(n: int, signals: int) -> int:
    return _pk("batch_score", "metal", n, signals=signals)

def pk_telecom_cpu(n: int, signals: int) -> int:
    """Portable kernel (spatial.kernel): a telecom billing/fraud score, on the CPU. SAME kernel as pk_batch_score (`batch_score`
    in spatial.kernel.library), only the name and docs differ: synthetic signals, no trained model,
    no real data for this vertical. See docs/KERNELS.md."""
    return _pk("batch_score", "cpu", n, signals=signals)


def pk_telecom_metal(n: int, signals: int) -> int:
    return _pk("batch_score", "metal", n, signals=signals)


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


def heat_numpy(n: int, steps: int, c: float = 0.2) -> float:
    """Simulation engine: 2-D heat diffusion from a hot square; returns the peak temperature."""
    import numpy as np
    from ..simulation.heat import simulate
    u0 = np.zeros((n, n))
    u0[n // 2 - n // 10: n // 2 + n // 10 + 1, n // 2 - n // 10: n // 2 + n // 10 + 1] = 100.0
    return float(simulate(u0, c, steps, "numpy").max())


def heat_numba(n: int, steps: int, c: float = 0.2) -> float:
    import numpy as np
    from ..simulation.heat import simulate
    u0 = np.zeros((n, n))
    u0[n // 2 - n // 10: n // 2 + n // 10 + 1, n // 2 - n // 10: n // 2 + n // 10 + 1] = 100.0
    return float(simulate(u0, c, steps, "numba").max())


def nbody(bodies: int, steps: int, seed: int = 1) -> float:
    """Simulation engine: relative energy drift of a leapfrog N-body run (should be tiny)."""
    import numpy as np
    from ..simulation import nbody as nb
    rng = np.random.default_rng(seed)
    pos, vel, mass = rng.normal(size=(bodies, 3)), rng.normal(size=(bodies, 3)) * 0.1, rng.uniform(0.5, 1.5, bodies)
    e0 = nb.energy(pos, vel, mass, 0.05)
    p, v = nb.leapfrog(pos, vel, mass, dt=1e-3, steps=steps, soft=0.05)
    return float(abs(nb.energy(p, v, mass, 0.05) - e0) / abs(e0))


def hologram_peak(n: int, seed: int = 1) -> int:
    """Holographic engine: synthesise a 1-point hologram, reconstruct it, return the focus position
    (row * n + column) of the brightest pixel (it must be the emitter's pixel)."""
    import numpy as np
    from ..holographic import hologram, reconstruct
    wl, pitch = 633e-9, 8e-6
    k = int(np.random.default_rng(seed).integers(-n // 8, n // 8 + 1))
    H = hologram(np.array([[k * pitch, 0.0, 0.05]]), np.array([1.0]), n, pitch, wl)
    img = reconstruct(H, 0.05, pitch, wl)
    return int(np.argmax(img))


def option_mc(paths: int, seed: int = 0) -> float:
    """Scientific engine: Monte-Carlo European call price (Black-Scholes reference exists in tests)."""
    from ..scientific import european_call_mc
    return float(european_call_mc(100.0, 105.0, 0.03, 0.2, 1.0, paths, seed)[0])


def harmonic_rk4_x(omega: float, t_end: float, steps: int) -> float:
    """Scientific engine: RK4 solution of x'' = -omega^2 x at t_end (exact: cos(omega * t_end))."""
    from ..scientific import harmonic_rk4
    return float(harmonic_rk4(omega, t_end, steps)[0])


REGISTRY = {
    "mandel_python": mandel_python,
    "mandel_numpy": mandel_numpy,
    "montecarlo_pi": montecarlo_pi,
    "sha256_chain": sha256_chain,
    "matmul": matmul,
    "mandel_f32_cpu": mandel_f32_cpu,
    "mandel_f32_metal": mandel_f32_metal,
    "mandel_f32_cuda": mandel_f32_cuda,
    "pk_mandel_cpu": pk_mandel_cpu,
    "pk_mandel_metal": pk_mandel_metal,
    "pk_collatz_cpu": pk_collatz_cpu,
    "pk_collatz_metal": pk_collatz_metal,
    "pk_batch_score_cpu": pk_batch_score_cpu,
    "pk_batch_score_metal": pk_batch_score_metal,
    "pk_rtb_cpu": pk_rtb_cpu,
    "pk_rtb_metal": pk_rtb_metal,
    "pk_credit_cpu": pk_credit_cpu,
    "pk_credit_metal": pk_credit_metal,
    "pk_claims_cpu": pk_claims_cpu,
    "pk_claims_metal": pk_claims_metal,
    "pk_alerts_cpu": pk_alerts_cpu,
    "pk_alerts_metal": pk_alerts_metal,
    "pk_moderation_cpu": pk_moderation_cpu,
    "pk_moderation_metal": pk_moderation_metal,
    "pk_telecom_cpu": pk_telecom_cpu,
    "pk_telecom_metal": pk_telecom_metal,
    "heat_numpy": heat_numpy,
    "heat_numba": heat_numba,
    "nbody": nbody,
    "hologram_peak": hologram_peak,
    "option_mc": option_mc,
    "harmonic_rk4": harmonic_rk4_x,
}
if HAVE_NUMBA:
    REGISTRY["mandel_numba"] = mandel_numba
    REGISTRY["mandel_numba_parallel"] = mandel_numba_parallel


def run(name: str, **params):
    if name not in REGISTRY:
        raise KeyError(f"workload '{name}' is not whitelisted")
    return REGISTRY[name](**params)

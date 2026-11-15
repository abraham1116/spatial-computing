"""Explicit finite-difference heat equation u_t = alpha * laplacian(u), insulated borders."""
from __future__ import annotations

import numpy as np

try:
    from numba import njit
    HAVE_NUMBA = True
except Exception:  # pragma: no cover
    HAVE_NUMBA = False


def stable_dt(alpha: float, dx: float) -> float:
    """Largest stable time step for the explicit scheme in 2-D (CFL): dx^2 / (4 alpha)."""
    return dx * dx / (4 * alpha)


def step_numpy(u: np.ndarray, c: float) -> np.ndarray:
    """c = alpha*dt/dx^2 (must be <= 0.25). Neumann (zero-flux) boundaries via edge padding."""
    p = np.pad(u, 1, mode="edge")
    return u + c * (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] - 4 * u)


if HAVE_NUMBA:
    @njit(cache=True)
    def step_numba(u, c):
        n, m = u.shape
        out = np.empty_like(u)
        for i in range(n):
            for j in range(m):
                up = u[i - 1, j] if i > 0 else u[i, j]
                dn = u[i + 1, j] if i < n - 1 else u[i, j]
                lf = u[i, j - 1] if j > 0 else u[i, j]
                rt = u[i, j + 1] if j < m - 1 else u[i, j]
                out[i, j] = u[i, j] + c * (up + dn + lf + rt - 4 * u[i, j])
        return out
else:  # pragma: no cover
    step_numba = step_numpy


def simulate(u0: np.ndarray, c: float, steps: int, backend: str = "numpy") -> np.ndarray:
    if c > 0.25:
        raise ValueError("unstable: c = alpha*dt/dx^2 must be <= 0.25")
    f = step_numba if backend == "numba" else step_numpy
    u = u0.astype(np.float64)
    for _ in range(steps):
        u = f(u, c)
    return u

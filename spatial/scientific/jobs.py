from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from ..compute.monitor import Measure
from ..core.model import Measurement


def black_scholes_call(s0: float, k: float, r: float, sigma: float, t: float) -> float:
    d1 = (math.log(s0 / k) + (r + sigma * sigma / 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    cdf = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    return s0 * cdf(d1) - k * math.exp(-r * t) * cdf(d2)


def european_call_mc(s0: float, k: float, r: float, sigma: float, t: float, paths: int,
                     seed: int = 0) -> tuple[float, float]:
    """Returns (price, standard error). Antithetic variates."""
    rng = np.random.default_rng(seed)
    acc = acc2 = 0.0
    n = 0
    left = paths // 2
    drift, vol = (r - sigma * sigma / 2) * t, sigma * math.sqrt(t)
    disc = math.exp(-r * t)
    while left > 0:
        m = min(left, 1_000_000)
        z = rng.standard_normal(m)
        pay = 0.5 * disc * (np.maximum(s0 * np.exp(drift + vol * z) - k, 0)
                            + np.maximum(s0 * np.exp(drift - vol * z) - k, 0))
        acc += float(pay.sum())
        acc2 += float((pay * pay).sum())
        n += m
        left -= m
    mean = acc / n
    return mean, math.sqrt(max(acc2 / n - mean * mean, 0) / n)


def harmonic_rk4(omega: float, t_end: float, steps: int) -> tuple[float, float]:
    """x'' = -omega^2 x, x(0)=1, v(0)=0, integrated with RK4. Returns (x(t_end), error bound).
    The bound is the RK4 global error scale (omega*dt)^4 * omega*t_end, used as the tolerance."""
    dt = t_end / steps
    x, v = 1.0, 0.0
    f = lambda x, v: (v, -omega * omega * x)
    for _ in range(steps):
        k1 = f(x, v)
        k2 = f(x + dt / 2 * k1[0], v + dt / 2 * k1[1])
        k3 = f(x + dt / 2 * k2[0], v + dt / 2 * k2[1])
        k4 = f(x + dt * k3[0], v + dt * k3[1])
        x += dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        v += dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
    return x, (omega * dt) ** 4 * omega * t_end


@dataclass
class JobSpec:
    name: str
    sector: str
    fn: Callable[[], tuple[float, float]]        # returns (value, standard error)
    reference: float | None = None
    tolerance_sigmas: float = 4.0
    tags: list[str] = field(default_factory=list)


def run_job(job: JobSpec) -> Measurement:
    out = {}
    with Measure("scientific", job.name, "local_numpy", power=False) as m:
        out["v"], out["se"] = job.fn()
    if m.ok:
        m.metrics.update(value=out["v"], std_error=out["se"], reference=job.reference)
        if job.reference is not None:
            dev = abs(out["v"] - job.reference) / max(out["se"], 1e-300)
            m.metrics["deviation_sigmas"] = dev
            m.ok = dev <= job.tolerance_sigmas
            if not m.ok:
                m.notes = "validation against reference failed"
    return m

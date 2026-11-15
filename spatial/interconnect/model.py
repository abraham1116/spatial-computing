"""alpha-beta cost model of one-way transfers:  t(M) = alpha + M / beta   (seconds, bytes, bytes/s).

Predicted all-reduce time of M bytes over N ranks (standard results, e.g. Thakur et al. 2005):
  ring              2 (N-1) alpha + 2 (N-1)/N * M/beta          bandwidth-optimal, latency grows with N
  halving_doubling  2 log2(N) alpha + 2 (N-1)/N * M/beta        N a power of two; bandwidth-optimal, low latency
  tree              2 log2(N) (alpha + M/beta)                  any N; latency-optimal, moves the full message
"""
from __future__ import annotations

import math

import numpy as np


def is_pow2(n: int) -> bool:
    return n >= 1 and n & (n - 1) == 0


def predict(algo: str, n: int, nbytes: float, alpha: float, beta: float) -> float:
    if n == 1:
        return 0.0
    lg = math.ceil(math.log2(n))
    if algo == "ring":
        return 2 * (n - 1) * alpha + 2 * (n - 1) / n * nbytes / beta
    if algo == "halving_doubling":
        if not is_pow2(n):
            return float("inf")
        return 2 * lg * alpha + 2 * (n - 1) / n * nbytes / beta
    if algo == "tree":
        return 2 * lg * (alpha + nbytes / beta)
    raise ValueError(f"unknown algorithm {algo}")


def choose(n: int, nbytes: float, alpha: float, beta: float) -> tuple[str, dict]:
    times = {a: predict(a, n, nbytes, alpha, beta) for a in ("ring", "halving_doubling", "tree")}
    return min(times, key=times.get), times


def fit_link(samples: list[tuple[int, float]]) -> tuple[float, float]:
    """Weighted least-squares fit of (alpha, beta) from (bytes, one-way seconds) samples.
    Rows are weighted by 1/time (relative error): otherwise the large messages, whose times are
    thousands of times bigger, would swamp the intercept and give a meaningless latency."""
    sizes = np.array([s for s, _ in samples], dtype=float)
    times = np.array([t for _, t in samples], dtype=float)
    w = 1.0 / times
    A = np.vstack([np.ones_like(sizes), sizes]).T * w[:, None]
    (alpha, inv_beta), *_ = np.linalg.lstsq(A, times * w, rcond=None)
    alpha = min(max(float(alpha), 1e-7), float(times.min()))        # latency cannot exceed the smallest measured transfer
    beta = 1.0 / max(float(inv_beta), 1e-15)
    return alpha, beta


def coefficients(algo: str, n: int) -> tuple[float, float]:
    """(A, B) such that predicted time = A * alpha + B * M / beta."""
    lg = math.ceil(math.log2(n))
    return {"ring": (2 * (n - 1), 2 * (n - 1) / n),
            "halving_doubling": (2 * lg, 2 * (n - 1) / n),
            "tree": (2 * lg, 2 * lg)}[algo]


def fit_algo(algo: str, n: int, samples: list[tuple[int, float]]) -> tuple[float, float]:
    """Effective (alpha, beta) of ONE algorithm from its measured all-reduce times (bytes, seconds).
    One shared link model is wrong in practice (software overhead differs per algorithm: how many
    sends and receives each rank does per step), so each algorithm is calibrated on its own history,
    like every other estimate in the planner."""
    a, b = coefficients(algo, n)
    sizes = np.array([s for s, _ in samples], dtype=float)
    times = np.array([t for _, t in samples], dtype=float)
    w = 1.0 / times
    M = np.vstack([np.full_like(sizes, a), b * sizes]).T * w[:, None]
    (alpha, inv_beta), *_ = np.linalg.lstsq(M, times * w, rcond=None)
    return max(float(alpha), 1e-7), 1.0 / max(float(inv_beta), 1e-15)


def choose_calibrated(n: int, nbytes: float, fits: dict[str, tuple[float, float]]) -> tuple[str, dict]:
    times = {a: predict(a, n, nbytes, *fits[a]) for a in fits if not (a == "halving_doubling" and not is_pow2(n))}
    return min(times, key=times.get), times

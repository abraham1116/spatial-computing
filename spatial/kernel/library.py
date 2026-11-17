"""Kernels written in the portable language. Each runs unchanged on CPU and Metal; CUDA C, HIP, and Triton are generated."""
from .dsl import kernel


@kernel
def mandelbrot(i: int, j: int, n: int, iters: int):
    ci = -1.3 + 2.6 * float(i) / float(n)
    cr = -2.0 + 2.6 * float(j) / float(n)
    zr = 0.0
    zi = 0.0
    k = 0
    while k < iters and zr * zr + zi * zi <= 4.0:
        t = zr * zr - zi * zi + cr
        zi = 2.0 * zr * zi + ci
        zr = t
        k += 1
    return k


@kernel
def collatz(i: int, j: int, n: int, limit: int):
    """Steps of the 3x+1 map from the start value i*n+j+1, capped at `limit` (pure integer code)."""
    x = i * n + j + 1
    k = 0
    while x != 1 and k < limit:
        if x % 2 == 0:
            x = x // 2
        else:
            x = 3 * x + 1
        k += 1
    return k


@kernel
def waves(i: int, j: int, n: int, terms: int):
    """Sum of `terms` damped sines (float transcendental code); returns a quantised value >= 0."""
    x = float(i) / float(n)
    y = float(j) / float(n)
    s = 0.0
    for k in range(terms):
        f = float(k + 1)
        s += sin(f * 6.2831853 * x) * cos(f * 3.1415927 * y) / f
    return int((s + 8.0) * 1000.0)


@kernel
def batch_score(i: int, j: int, n: int, signals: int):
    """A batch-scoring kernel: element (i, j) is one of n*n independent items, scored by combining
    `signals` weighted features through a logistic sum — the same shape as scoring a transaction for
    fraud/credit risk, ranking a search or ad result, flagging an anomaly, or filtering content, whichever
    software already does that scoring in a batch or a stream. The features and weights here are SYNTHETIC
    (no real data, no trained model): this demonstrates that the planner places and measures a batch-scoring
    job exactly like it places Mandelbrot or Collatz, not a validated scoring model for any one domain.
    Returns the score quantised to [0, 10000] (hundredths of a percent)."""
    idx = i * n + j
    x1 = float(idx % 2000) / 20.0 - 50.0
    x2 = float(i) / float(n) - 0.5
    z = 0.0
    k = 0
    while k < signals:
        w = sin(float(k + 1) * 0.37) * 1.3
        z += w * (x1 / (float(k) + 1.0) + x2)
        k += 1
    p = 1.0 / (1.0 + exp(-z))
    return int(p * 10000.0)


LIBRARY = {"mandelbrot": mandelbrot, "collatz": collatz, "waves": waves, "batch_score": batch_score}

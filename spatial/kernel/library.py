"""Kernels written in the portable language. Each runs unchanged on CPU and Metal; CUDA C is generated."""
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


LIBRARY = {"mandelbrot": mandelbrot, "collatz": collatz, "waves": waves}

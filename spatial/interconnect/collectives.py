"""Collectives built on Comm.send/recv: all-reduce (sum) three ways, and broadcast."""
from __future__ import annotations

import math

import numpy as np

from .model import choose, is_pow2

ALGOS = ("ring", "halving_doubling", "tree")


def _bounds(total: int, parts: int) -> list[tuple[int, int]]:
    edges = np.linspace(0, total, parts + 1).astype(int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(parts)]


def ring_allreduce(comm, x: np.ndarray, tag) -> np.ndarray:
    n, r = comm.size, comm.rank
    buf = x.astype(np.float32, copy=True)
    ch = _bounds(len(buf), n)
    nxt, prv = (r + 1) % n, (r - 1) % n
    for s in range(n - 1):                                   # reduce-scatter
        a, b = ch[(r - s) % n]
        comm.send(nxt, (tag, "rs", s), buf[a:b])
        a, b = ch[(r - s - 1) % n]
        buf[a:b] += comm.recv(prv, (tag, "rs", s))
    for s in range(n - 1):                                   # all-gather
        a, b = ch[(r + 1 - s) % n]
        comm.send(nxt, (tag, "ag", s), buf[a:b])
        a, b = ch[(r - s) % n]
        buf[a:b] = comm.recv(prv, (tag, "ag", s))
    return buf


def halving_doubling_allreduce(comm, x: np.ndarray, tag) -> np.ndarray:
    n, r = comm.size, comm.rank
    if not is_pow2(n):
        raise ValueError("halving_doubling needs a power-of-two number of ranks")
    buf = x.astype(np.float32, copy=True)
    lo, hi = 0, len(buf)
    steps = []                                               # (keep, send) bounds per halving step
    d = n // 2
    while d >= 1:                                            # recursive halving (reduce-scatter)
        mid = lo + (hi - lo) // 2
        keep, send = ((lo, mid), (mid, hi)) if r & d == 0 else ((mid, hi), (lo, mid))
        partner = r ^ d
        comm.send(partner, (tag, "h", d), buf[send[0]:send[1]])
        buf[keep[0]:keep[1]] += comm.recv(partner, (tag, "h", d))
        steps.append((keep, send, d))
        lo, hi = keep
        d //= 2
    for keep, send, d in reversed(steps):                    # recursive doubling (all-gather)
        partner = r ^ d
        comm.send(partner, (tag, "g", d), buf[keep[0]:keep[1]])
        buf[send[0]:send[1]] = comm.recv(partner, (tag, "g", d))
    return buf


def tree_allreduce(comm, x: np.ndarray, tag) -> np.ndarray:
    n, r = comm.size, comm.rank
    buf = x.astype(np.float32, copy=True)
    d = 1
    while d < n:                                             # binomial reduce to rank 0
        if r % (2 * d) == 0:
            if r + d < n:
                buf += comm.recv(r + d, (tag, "r", d))
        elif r % (2 * d) == d:
            comm.send(r - d, (tag, "r", d), buf)
            break
        d *= 2
    return broadcast(comm, buf, 0, (tag, "b"))


def broadcast(comm, x: np.ndarray, root: int, tag) -> np.ndarray:
    """Binomial-tree broadcast from `root`."""
    n = comm.size
    rel = (comm.rank - root) % n
    buf = x.astype(np.float32, copy=True)
    top = 1 << (math.ceil(math.log2(n)) - 1) if n > 1 else 0
    d = top
    have = rel == 0
    while d >= 1:
        if have and rel % (2 * d) == 0 and rel + d < n:
            comm.send((rel + d + root) % n, (tag, d), buf)
        elif not have and rel % (2 * d) == d:
            buf = comm.recv((rel - d + root) % n, (tag, d))
            have = True
        d //= 2
    return buf


def allreduce(comm, x: np.ndarray, algo: str = "auto", tag="ar", alpha: float | None = None, beta: float | None = None) -> np.ndarray:
    """Sum of x over all ranks, on every rank. algo = ring | halving_doubling | tree | auto
    (auto uses the alpha-beta model; pass measured alpha/beta, e.g. from tasks.measure_link)."""
    if comm.size == 1:
        return x.astype(np.float32, copy=True)
    if algo == "auto":
        if alpha is None or beta is None:
            raise ValueError("auto needs alpha and beta (measure them with tasks.measure_link)")
        algo, _ = choose(comm.size, x.nbytes, alpha, beta)
    return {"ring": ring_allreduce, "halving_doubling": halving_doubling_allreduce, "tree": tree_allreduce}[algo](comm, x, tag)

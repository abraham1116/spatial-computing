"""Functions executed on every rank (must live in an importable module because ranks are spawned)."""
from __future__ import annotations

import statistics
import time

import numpy as np

from .collectives import allreduce, broadcast
from .model import fit_link, predict


def measure_link(comm, sizes=(64, 1 << 16, 1 << 20, 8 << 20), reps: int = 5):
    """Ping-pong between rank 0 and 1, then share (alpha, beta) with every rank. One-way time = round trip / 2."""
    samples = []
    if comm.size >= 2 and comm.rank in (0, 1):
        for sz in sizes:
            x = np.zeros(max(sz // 4, 1), np.float32)
            best = float("inf")
            for k in range(reps + 1):                              # first round warms the connection
                t0 = time.perf_counter()
                if comm.rank == 0:
                    comm.send(1, ("pp", sz, k), x)
                    comm.recv(1, ("pp", sz, k))
                else:
                    comm.recv(0, ("pp", sz, k))
                    comm.send(0, ("pp", sz, k), x)
                if k:
                    best = min(best, (time.perf_counter() - t0) / 2)
            samples.append((x.nbytes, best))
    ab = np.zeros(2, np.float32)
    if comm.rank == 0:
        a, b = fit_link(samples)
        ab[:] = (a, np.float32(b))
    ab = broadcast(comm, ab, 0, "ab")
    # beta can exceed float32 precision needs: it is a rate, relative precision 1e-7 is plenty
    return float(ab[0]), float(ab[1])


def check_allreduce(comm, algo: str, n_elems: int, seed: int = 0):
    """Every rank contributes a deterministic vector; returns the worst deviation from the exact sum."""
    rngs = [np.random.default_rng(seed + r) for r in range(comm.size)]
    vecs = [g.standard_normal(n_elems).astype(np.float32) for g in rngs]
    exact = np.sum(vecs, axis=0, dtype=np.float64)
    out = allreduce(comm, vecs[comm.rank], algo, tag=("chk", algo))
    return float(np.max(np.abs(out - exact)))


def time_allreduce(comm, algo: str, n_elems: int, reps: int = 5):
    x = np.random.default_rng(comm.rank).standard_normal(n_elems).astype(np.float32)
    allreduce(comm, x, algo, tag=("w", algo, n_elems))               # warm-up
    ts = []
    for k in range(reps):
        comm.barrier(("t", algo, n_elems, k))
        t0 = time.perf_counter()
        allreduce(comm, x, algo, tag=("t", algo, n_elems, k))
        ts.append(time.perf_counter() - t0)
    return statistics.median(ts)


def bench_all(comm, sizes_elems, algos, reps: int = 5):
    """Link fit, then the median time of each algorithm at each size, with the model's prediction."""
    alpha, beta = measure_link(comm)
    rows = []
    for ne in sizes_elems:
        row = {"elems": ne, "bytes": ne * 4, "measured_s": {}, "predicted_s": {}}
        for a in algos:
            row["predicted_s"][a] = predict(a, comm.size, ne * 4, alpha, beta)
            if row["predicted_s"][a] != float("inf"):
                row["measured_s"][a] = time_allreduce(comm, a, ne, reps)
        rows.append(row)
    return {"alpha_s": alpha, "beta_Bps": beta, "rows": rows}

"""Strategy comparison and selection for the Spatial Compute Engine.

compare(): run every feasible strategy for a task, MEASURE it, verify the result
matches the reference, then choose() by objective (time | cpu | energy).
"""
from __future__ import annotations

import multiprocessing as mp
import threading
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Callable

from ..core.ledger import Ledger
from ..core.model import Measurement, Node, ResourceKind
from . import workloads
from .monitor import Measure


def _chunk(args):
    name, params = args
    return workloads.run(name, **params)


def _row_chunks(n: int, parts: int) -> list[tuple[int, int]]:
    step = max(1, n // parts)
    return [(r, min(n, r + step)) for r in range(0, n, step)]


@dataclass
class Strategy:
    name: str
    fn: Callable[[dict], object]
    kind: str   # local | optimized | parallel | distributed | remote
    needs_worker: bool = False


class ComputeScheduler:
    def __init__(self, node: Node, ledger: Ledger | None = None, worker_client=None):
        self.node = node
        self.ledger = ledger or Ledger()
        self.worker = worker_client
        self.cores = int(node.by_kind(ResourceKind.CPU)[0].capacity)
        self._pool = None

    # ---- mandelbrot family -------------------------------------------------
    def mandel_strategies(self) -> list[Strategy]:
        S = [
            Strategy("local_python", lambda p: workloads.mandel_python(**p), "local"),
            Strategy("local_numpy", lambda p: workloads.mandel_numpy(**p), "optimized"),
        ]
        if workloads.HAVE_NUMBA:
            S += [
                Strategy("local_numba_jit", lambda p: workloads.mandel_numba(**p), "optimized"),
                Strategy("local_numba_threads", lambda p: workloads.mandel_numba_parallel(**p), "parallel"),
                Strategy("multiprocess_numba", self._mp, "parallel"),
                Strategy("multiprocess_warm_pool", self._mp_warm, "parallel"),
            ]
            if self.worker is not None:
                S += [
                    Strategy("remote_worker", self._remote, "remote", needs_worker=True),
                    Strategy("distributed_local+worker", self._distributed, "distributed", needs_worker=True),
                ]
        return S

    def _mp(self, p: dict):
        chunks = _row_chunks(p["n"], self.cores * 8)
        with ProcessPoolExecutor(self.cores, mp_context=mp.get_context("spawn")) as ex:
            return sum(ex.map(_chunk, [("mandel_numba", {**p, "r0": a, "r1": b}) for a, b in chunks]))

    def _mp_warm(self, p: dict):
        """Same split as _mp but on a pool started (and JIT-warmed) beforehand: isolates the
        cost of process start-up + imports that _mp pays on every call."""
        if self._pool is None:
            self._start_pool()
        chunks = _row_chunks(p["n"], self.cores * 8)
        return sum(self._pool.map(_chunk, [("mandel_numba", {**p, "r0": a, "r1": b}) for a, b in chunks]))

    def _start_pool(self):
        self._pool = ProcessPoolExecutor(self.cores, mp_context=mp.get_context("spawn"))
        list(self._pool.map(_chunk, [("mandel_numba", {"n": 8, "iters": 8})] * (self.cores * 4)))

    def close(self):
        if self._pool is not None:
            self._pool.shutdown()
            self._pool = None

    def _remote(self, p: dict):
        rh, _ = self.worker.call({"op": "run", "workload": "mandel_numba", "params": p})
        self._last_remote = rh
        return rh["result"]

    def _distributed(self, p: dict):
        """Interleave row chunks: odd chunks to the worker, even chunks locally."""
        chunks = _row_chunks(p["n"], 32)
        mine, theirs = chunks[0::2], chunks[1::2]
        out = {}

        def remote():
            tot = 0
            for a, b in theirs:
                rh, _ = self.worker.call({"op": "run", "workload": "mandel_numba",
                                          "params": {**p, "r0": a, "r1": b}})
                tot += rh["result"]
            out["r"] = tot

        t = threading.Thread(target=remote)
        t.start()
        local = sum(workloads.mandel_numba(**{**p, "r0": a, "r1": b}) for a, b in mine)
        t.join()
        return local + out["r"]

    # ---- generic -----------------------------------------------------------
    def warmup(self):
        """Compile JIT code outside the timed region (compile time is reported separately)."""
        if workloads.HAVE_NUMBA:
            workloads.mandel_numba(8, 8)
            workloads.mandel_numba_parallel(8, 8)
            if self._pool is None:
                self._start_pool()
            if self.worker is not None:
                self.worker.call({"op": "run", "workload": "mandel_numba", "params": {"n": 8, "iters": 8}})

    def compare(self, experiment: str, params: dict, strategies: list[Strategy],
                reference: object | None = None, skip: set[str] = frozenset()) -> list[Measurement]:
        rows = []
        for s in strategies:
            if s.name in skip:
                continue
            holder = {}
            with Measure("compute", experiment, s.name) as m:
                holder["r"] = s.fn(dict(params))
            m.metrics["kind"] = s.kind
            m.metrics["params"] = params
            if m.ok:
                if reference is None:
                    reference = holder["r"]
                m.metrics["result"] = holder["r"]
                m.metrics["matches_reference"] = holder["r"] == reference
                if not m.metrics["matches_reference"]:
                    m.ok = False
                    m.notes = "result differs from reference"
            if s.needs_worker and m.ok:
                m.notes = "worker is a separate process on this same machine (loopback)"
            rows.append(self.ledger.record(m))
        return rows

    def predict_best(self, n: int, iters: int) -> tuple[str, float] | None:
        """Ask the Intelligence Engine which strategy should be fastest for this size, from the
        ledger's past measurements, WITHOUT running anything. None when history is too thin."""
        from ..intelligence import PowerLawPredictor
        return PowerLawPredictor.from_ledger(self.ledger.rows()).best(n * n * iters)

    def choose(self, rows: list[Measurement], objective: str = "time") -> Measurement:
        ok = [r for r in rows if r.ok]
        if not ok:
            raise RuntimeError("no strategy succeeded")
        if objective == "cost":            # $ = CPU-seconds actually burnt, priced per core-hour
            usd_core_h = getattr(self, "usd_per_core_hour", 0.045)     # assumption, override on the instance
            for r in ok:
                r.cost_usd = (r.cpu_s or r.wall_s) / 3600 * usd_core_h
        key = {"time": lambda r: r.wall_s, "cpu": lambda r: r.cpu_s, "cost": lambda r: r.cost_usd,
               "energy": lambda r: r.energy_j if r.energy_j is not None else float("inf")}[objective]
        best = min(ok, key=key)
        self.ledger.decide("compute", f"choose {best.strategy}", f"min {objective}",
                           experiment=best.experiment,
                           candidates={r.strategy: round(key(r), 4) for r in ok if key(r) != float("inf")})
        return best

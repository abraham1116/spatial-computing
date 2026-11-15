"""Providers: how each engine turns a job into priced, comparable options.

compute   numerical families (Compute, Simulation, Scientific, Holographic engines): each variant is probed
          on a reduced problem, checked against the others, and extrapolated
fleet     the same compute job on each node of a fleet hub, priced at the node's own rate
memory    a dataset: all in RAM, or tiered over SSD, with tier latencies measured on this machine
runtime   a binary: every route (native, WASM, micro-VM, Wine) with its isolation and measured overhead
quantum   a circuit: exact simulator, Qiskit Aer, or real hardware (only if asked for and priced)
kv        an inference cache prefix: recompute it, or keep and restore it (toy model, measured)
"""
from __future__ import annotations

import math
import os
import tempfile
import time
from pathlib import Path

import numpy as np
import psutil

from ..compute import workloads
from .model import Job, Objective, Option, Validated

ROOT = Path(__file__).resolve().parents[2]

# family: variants (name -> registered workload), the parameter that scales the work, how the work grows
# with it, the smallest valid value, and whether variants must agree exactly or to a tolerance.
FAMILIES = {
    "mandel": dict(variants={"python": "mandel_python", "numpy": "mandel_numpy", "numba_jit": "mandel_numba",
                             "numba_threads": "mandel_numba_parallel"}, scale="n", exp=2.0, min=8, exact=True),
    # one job, three devices: the planner picks by measured cost (CPU for small sizes, the GPU once its fixed cost is amortised)
    "mandel_f32": dict(variants={"cpu": "mandel_f32_cpu", "gpu_metal": "mandel_f32_metal", "gpu_cuda": "mandel_f32_cuda"},
                       scale="n", exp=2.0, min=8, exact=False, tol=1e-3),
    "heat": dict(variants={"numpy": "heat_numpy", "numba": "heat_numba"}, scale="steps", exp=1.0, min=2, exact=False),
    "nbody": dict(variants={"cpu": "nbody"}, scale="steps", exp=1.0, min=2, exact=False),
    "hologram": dict(variants={"cpu": "hologram_peak"}, scale="n", exp=2.0, min=32, exact=True),
    "option": dict(variants={"cpu": "option_mc"}, scale="paths", exp=1.0, min=1000, exact=False),
    "ode": dict(variants={"cpu": "harmonic_rk4"}, scale="steps", exp=1.0, min=10, exact=False),
}


def _same(a, b, exact: bool, tol: float = 1e-6) -> bool:
    return a == b if exact else math.isclose(a, b, rel_tol=tol, abs_tol=1e-12)


def _variant_available(workload: str) -> str | None:
    """None if the variant can run here, else why not."""
    if workload == "mandel_f32_metal":
        from ..fabric import metal
        return None if metal.available() else "no Metal GPU (macOS with swiftc is required)"
    if workload == "mandel_f32_cuda":
        from ..fabric import cuda
        return None if cuda.available() else "no NVIDIA GPU usable by numba.cuda on this machine"
    return None


def _best_of(fn, min_total_s: float = 0.01, max_reps: int = 25):
    """Run fn repeatedly (at least 3 times, until ~10 ms in total) and return (minimum time, last result).
    Microsecond-scale probes are dominated by noise; the minimum is the least disturbed run."""
    best, total, n, res = float("inf"), 0.0, 0, None
    while n < 3 or (total < min_total_s and n < max_reps):
        t0 = time.perf_counter()
        res = fn()
        dt = time.perf_counter() - t0
        best, total, n = min(best, dt), total + dt, n + 1
    return best, res


class Provider:
    kinds: tuple = ()

    def options(self, job: Job, obj: Objective, planner, so_far: list) -> list[Option]:
        raise NotImplementedError


# ------------------------------------------------------------------------------------- compute
class ComputeProvider(Provider):
    kinds = ("compute",)

    def options(self, job, obj, planner, so_far):
        fam_name, params = job.spec["family"], dict(job.spec["params"])
        if fam_name not in FAMILIES:
            raise KeyError(f"unknown compute family '{fam_name}' (known: {', '.join(FAMILIES)})")
        fam = FAMILIES[fam_name]
        scale, s = fam["scale"], params[fam["scale"]]
        small = s <= fam["min"] * 4                                               # tiny job: run it in full, no extrapolation
        s1, s2 = (s, s) if small else (max(fam["min"], s // 8), max(fam["min"] * 2, s // 4))
        out, ref = [], None
        for vname, wname in fam["variants"].items():
            why = _variant_available(wname)
            if why:
                out.append(Option("compute", vname, False, why, isolated=None, basis="device not available"))
                continue
            workloads.run(wname, **{**params, scale: fam["min"]})                 # warm-up (JIT), not timed
            t1, r1 = _best_of(lambda: workloads.run(wname, **{**params, scale: s1}))
            if small:
                est, r, basis = t1, r1, "probe (full size)"
            else:
                t2, r = _best_of(lambda: workloads.run(wname, **{**params, scale: s2}))
                w1, w2, wf = s1 ** fam["exp"], s2 ** fam["exp"], s ** fam["exp"]
                b_ = (t2 - t1) / (w2 - w1)
                a_ = t1 - b_ * w1
                if b_ > 0 and a_ >= 0:                     # time = fixed cost + per-work cost: separates JIT/thread start-up from speed
                    est, basis = a_ + b_ * wf, f"probe 1/8+1/4, affine fit"
                else:                                      # noisy probes: fall back to proportional scaling from the larger one
                    est, basis = t2 * wf / w2, "probe 1/4, proportional"
            o = Option("compute", vname, True, est_time_s=est, rate_usd_h=planner.prices.device_usd_h.get(vname, planner.prices.local_usd_per_hour),
                       isolated=None, basis=basis,
                       run=(lambda wn=wname: workloads.run(wn, **params)), meta={"workload": wname, "params": params})
            if ref is None:
                ref = r
            elif not _same(r, ref, fam["exact"], fam.get("tol", 1e-6)):
                o.reject("result differs from the other variants on the probe")
            out.append(planner.calibrate("compute", o))
        return out


# ------------------------------------------------------------------------------------- fleet
class FleetProvider(Provider):
    kinds = ("compute",)

    def options(self, job, obj, planner, so_far):
        if planner.hub is None:
            return []
        cands = [o for o in so_far if o.engine == "compute" and o.feasible and o.est_time_s is not None]
        if not cands:
            return []
        best = min(cands, key=lambda o: o.est_time_s)
        rows = planner.hub.call({"op": "nodes"})[0]["nodes"]
        out = []
        for n in rows:
            o = Option("fleet", n["node"], True, isolated=None, meta={"workload": best.meta["workload"], "params": best.meta["params"]})
            if not obj.allow_remote:
                o.reject("remote nodes not allowed by this objective")
            elif not n["alive"]:
                o.reject("node is down")
            elif n["usd_per_hour"] is None:
                o.reject("node price unknown (agent started without --usd-per-hour)")
            else:
                busy = min(0.9, (n["cpu_avg"] or 0) / 100)
                o.est_time_s = best.est_time_s / (1 - busy)
                o.rate_usd_h = n["usd_per_hour"]
                o.basis = f"assumption: same speed as local '{best.name}', slowed by node load"
                o.run = (lambda node=n["node"]: self._remote(planner, node, best.meta["workload"], best.meta["params"]))
            out.append(o)
        return out

    @staticmethod
    def _remote(planner, node, workload, params, timeout_s=600):
        tid = planner.hub.call({"op": "submit", "workload": workload, "params": params, "needs": {"node": node}})[0]["task_id"]
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            t = planner.hub.call({"op": "task", "task_id": tid})[0]["task"]
            if t["state"] == "done":
                return t["result"]
            if t["state"] == "failed":
                raise RuntimeError(t.get("error"))
            time.sleep(0.1)
        raise TimeoutError(f"task {tid} on {node} did not finish in {timeout_s} s")


# ------------------------------------------------------------------------------------- memory
_LAT: dict = {}


def tier_latencies(page: int = 65536) -> dict:
    """Mean access latency (seconds) of the hot and far tiers of THIS machine, measured with the library."""
    if page in _LAT:
        return _LAT[page]
    from ..memory import FileBackend, TieredStore
    d = tempfile.mkdtemp(prefix="spatial-lat-")
    st = TieredStore(4 * page, 4 * page, FileBackend(os.path.join(d, "f")), codec_name="lz4")
    rng = np.random.default_rng(0)
    for i in range(48):
        st.put(i, np.cumsum(rng.integers(0, 3, page // 8)).astype(np.float64).tobytes())
    last = 47
    for _ in range(300):
        st.get(last)
    for i in range(16):
        st.get(i)
    s = st.stats()
    st.close()
    hot = (s["hot_mean_us"] or 1.0) * 1e-6
    far = (s["far_mean_us"] or s["compressed_mean_us"] or 200.0) * 1e-6
    _LAT[page] = {"hot": hot, "far": far}
    return _LAT[page]


def hit_ratio(total: float, budget: float, locality: float, hot_fraction: float) -> float:
    """Share of accesses served from RAM when `locality` of them go to the hottest `hot_fraction` of the data."""
    if budget >= total:
        return 1.0
    hot_bytes = hot_fraction * total
    if budget >= hot_bytes:
        return locality + (1 - locality) * (budget - hot_bytes) / max(total - hot_bytes, 1)
    return locality * budget / hot_bytes


class MemoryProvider(Provider):
    kinds = ("dataset",)

    def options(self, job, obj, planner, so_far):
        sp = job.spec
        T, N, L, f, page = sp["total_bytes"], sp["accesses"], sp["locality"], sp["hot_fraction"], sp["page_bytes"]
        budget = obj.max_ram_bytes if obj.max_ram_bytes is not None else int(0.5 * psutil.virtual_memory().available)
        lat = tier_latencies(page)
        P = planner.prices
        gb = lambda b: b / 1e9
        out = []
        o = Option("memory", "in_ram", True, est_time_s=N * lat["hot"], est_ram_bytes=T,
                   rate_usd_h=P.local_usd_per_hour + P.ram_usd_gb_hour * gb(T), isolated=None,
                   basis="measured hot-tier latency")
        if T > budget:
            o.reject(f"{T / 2**30:.1f} GiB does not fit the {budget / 2**30:.1f} GiB RAM budget")
        o.run = lambda: self._validate(job, budget, "in_ram", lat)
        out.append(o)
        p = hit_ratio(T, budget, L, f)
        free = psutil.disk_usage(tempfile.gettempdir()).free
        o = Option("memory", "tiered_ssd", True, est_time_s=N * (p * lat["hot"] + (1 - p) * lat["far"]),
                   est_ram_bytes=min(budget, T),
                   rate_usd_h=P.local_usd_per_hour + P.ram_usd_gb_hour * gb(min(budget, T)) + P.storage_usd_gb_hour * gb(T),
                   isolated=None, basis=f"measured tiers, hit ratio {p:.2f} (locality model)", meta={"hit_ratio": p})
        if T / 2 > free:
            o.reject(f"needs about {T / 2 / 2**30:.0f} GiB of free disk, {free / 2**30:.0f} GiB available")
        o.run = lambda: self._validate(job, budget, "tiered_ssd", lat)
        out.append(planner.calibrate("dataset", o))
        return out

    @staticmethod
    def _validate(job, budget, name, lat):
        """Run the REAL tiered store at reduced scale (<= 64 MiB, <= 3000 accesses) and compare with the model."""
        from ..memory import FileBackend, TieredStore
        sp = job.spec
        page = sp["page_bytes"]
        scale = min(1.0, (64 << 20) / sp["total_bytes"])
        T = max(int(sp["total_bytes"] * scale), 16 * page)
        B = int(budget * scale) if name == "tiered_ssd" else T
        n_pages, N = T // page, min(sp["accesses"], 3000)
        d = tempfile.mkdtemp(prefix="spatial-val-")
        st = TieredStore(min(B, T), 2 * page, FileBackend(os.path.join(d, "f")), codec_name="lz4")
        rng = np.random.default_rng(1)
        for i in range(n_pages):
            st.put(i, np.cumsum(rng.integers(0, 3, page // 8)).astype(np.float64).tobytes())
        hot_n = max(1, int(sp["hot_fraction"] * n_pages))
        idx = np.where(rng.random(N) < sp["locality"], rng.integers(0, hot_n, N), rng.integers(0, n_pages, N))
        t0 = time.perf_counter()
        for i in idx:
            st.get(int(i))
        wall = time.perf_counter() - t0
        p = hit_ratio(T, min(B, T), sp["locality"], sp["hot_fraction"])
        est = N * (p * lat["hot"] + (1 - p) * lat["far"])
        st.close()
        return Validated({"validated_scale": scale, "pages": n_pages, "accesses": N, "mean_us": wall / N * 1e6,
                          "predicted_hit_ratio": p}, wall, est)


# ------------------------------------------------------------------------------------- runtime
ROUTE_CONSTANTS = {          # route: (slowdown vs native, startup seconds, isolated)   measured on the reference Mac
    "native": (1.00, 0.005, False), "wasm-node-wasi": (1.48, 0.07, True), "microvm-hvf": (1.04, 0.88, True),
    "microvm-tcg": (23.8, 3.4, True), "wine": (1.45, 4.5, False), "native-interpreter": (1.0, 0.05, False),
}


class RuntimeProvider(Provider):
    kinds = ("binary",)

    def options(self, job, obj, planner, so_far):
        from ..runtime import execute, inspect, plan
        sp = job.spec
        art = inspect(sp["path"])
        out = []
        for r in plan(art):
            slow, startup, iso = ROUTE_CONSTANTS.get(r.name, (None, None, None))
            o = Option("runtime", r.name, r.feasible, "" if r.feasible else r.reason, isolated=iso,
                       rate_usd_h=planner.prices.local_usd_per_hour, basis="constants measured on the reference Mac")
            if r.feasible and slow is not None:
                o.est_time_s = startup + sp["est_native_s"] * slow
            elif r.feasible:
                o.reject("no measured overhead for this route")
            o.run = (lambda name=r.name: self._run(execute, sp, name))
            out.append(o)
        return out

    @staticmethod
    def _run(execute, sp, route):
        e = execute(sp["path"], sp["args"], route=route)
        if not e.ok:
            raise RuntimeError(str(e.extra.get("not_runnable") or e.extra))
        return e.stdout


# ------------------------------------------------------------------------------------- quantum
class QuantumProvider(Provider):
    kinds = ("quantum",)

    def options(self, job, obj, planner, so_far):
        from ..q import compile_kernel, parse
        from ..q import backends as B
        sp = job.spec
        prog = parse(sp["source"])
        c, _ = compile_kernel(prog.kernels[sp["kernel"]], sp["args"], kernels=prog.kernels)
        est = c.estimate()
        P, shots = planner.prices, sp["shots"]
        out = []
        for name in ("statevector", "aer"):
            o = Option("quantum", name, True, isolated=None, rate_usd_h=P.local_usd_per_hour, est_ram_bytes=est.statevector_bytes)
            if obj.require_hardware:
                o.reject("real hardware required by this objective")
            elif est.statevector_bytes > 0.5 * psutil.virtual_memory().available:
                o.reject(f"{est.qubits} qubits need {est.statevector_bytes / 2**30:.1f} GiB for an exact state vector")
            else:
                try:
                    b = B.get(name)
                    b.sample(c, 10, 0)                                   # warm-up
                    o.est_time_s = _best_of(lambda: b.sample(c, 10, 0))[0] * (1 + shots / 5000)
                    o.basis = "probe (10 shots)"
                    o.run = (lambda b=b: b.sample(c, shots, 0))
                except B.BackendUnavailable as e:
                    o.reject(str(e))
            out.append(planner.calibrate("quantum", o))
        q = Option("quantum", "qpu", True, isolated=None, est_ram_bytes=None, basis="provider tariff supplied by the caller; queue time unknown")
        tok = B._ibm_token()
        if not obj.allow_qpu:
            q.reject("real hardware is only used when the objective allows it (allow_qpu)")
        elif tok is None:
            q.reject("no IBM Quantum token configured")
        elif not P.qpu_priced():
            q.reject("no QPU price given: refusing to guess a tariff")
        else:
            q.fixed_usd = c.shot_cost(shots, P.qpu_usd_per_shot, P.qpu_usd_per_task, P.qpu_usd_per_second, P.qpu_seconds_per_shot)["usd"]
            q.run = (lambda: B.QpuBackend().sample(c, shots, 0))
        out.append(q)
        return out


# ------------------------------------------------------------------------------------- kv cache
_KV: dict = {}


def _kv_fit():
    """Measure recompute and restore on the toy transformer at two sizes and fit power laws."""
    if "fit" in _KV:
        return _KV["fit"]
    from ..ai import ToyTransformer, measure_restore_vs_recompute
    from ..memory import FileBackend, TieredStore
    m = ToyTransformer(layers=4, d=64, heads=4)
    pts = []
    for P in (96, 192):
        d = tempfile.mkdtemp(prefix="spatial-kv-")
        st = TieredStore(1, 1, FileBackend(os.path.join(d, "f")), codec_name="lz4")
        r = measure_restore_vs_recompute(m, np.random.default_rng(0).integers(0, 256, P), st)
        st.close()
        pts.append((P, r["recompute_s"], r["restore_s"], r["cache_bytes"]))
    (p1, rc1, rs1, b1), (p2, rc2, rs2, b2) = pts
    # recompute: measured exponent, clamped to the physically sensible [1, 2] (prefill is linear to quadratic in tokens);
    # restore: linear in bytes, anchored on the larger probe (two noisy points must not decide the exponent)
    exp_rc = min(2.0, max(1.0, math.log(rc2 / rc1) / math.log(p2 / p1)))
    fit = {"model": m, "p_max": p2, "bytes_per_token": b2 / p2, "rc": (rc2, exp_rc, p2), "rs": (rs2, 1.0, p2)}
    _KV["fit"] = fit
    return fit


def _pl(fit, P):
    a, b, p0 = fit
    return a * (P / p0) ** b


class KvProvider(Provider):
    kinds = ("kv",)

    def options(self, job, obj, planner, so_far):
        sp = job.spec
        P, reuse, hours = sp["prefix_tokens"], sp["reuse_prob"], sp["horizon_h"]
        f = _kv_fit()
        rc, rs = _pl(f["rc"], P), _pl(f["rs"], P)
        size = f["bytes_per_token"] * P
        far = P > 8 * f["p_max"]
        basis = "toy model fit" + (", extrapolated >8x" if far else "") + "; expected time = reuse_prob x time"
        a = Option("kv", "recompute", True, est_time_s=reuse * rc, rate_usd_h=planner.prices.local_usd_per_hour, isolated=None, basis=basis,
                   run=lambda: self._validate(job, "recompute"))
        b = Option("kv", "restore", True, est_time_s=reuse * rs, rate_usd_h=planner.prices.local_usd_per_hour,
                   fixed_usd=planner.prices.storage_usd_gb_hour * size / 1e9 * hours, est_ram_bytes=0, isolated=None, basis=basis,
                   run=lambda: self._validate(job, "restore"))
        return [planner.calibrate("kv", a), planner.calibrate("kv", b)]

    @staticmethod
    def _validate(job, path):
        """Run the chosen path for real at 288 tokens; the cache restored from the store must give
        exactly the same logits as recomputation, and the time is compared with the fit."""
        from ..memory import FileBackend, TieredStore
        from ..ai.kvcache import cache_from_pages, cache_to_pages
        f = _kv_fit()
        m, P = f["model"], 288
        rng = np.random.default_rng(3)
        prefix, tail = rng.integers(0, 256, P), rng.integers(0, 256, 4)
        full, _ = m.forward(np.concatenate([prefix, tail]))
        if path == "recompute":
            t0 = time.perf_counter()
            _, cache = m.forward(prefix)
            wall, est = time.perf_counter() - t0, _pl(f["rc"], P)
        else:
            _, cache = m.forward(prefix)
            st = TieredStore(1, 1, FileBackend(os.path.join(tempfile.mkdtemp(prefix="spatial-kv-"), "f")), codec_name="lz4")
            for i, pg in enumerate(cache_to_pages(cache)):
                st.put(i, pg)
            t0 = time.perf_counter()
            cache = cache_from_pages([st.get(i) for i in range(len(cache) * 2)], m.d)
            wall, est = time.perf_counter() - t0, _pl(f["rs"], P)
            st.close()
        cont, _ = m.forward(tail, cache)
        return Validated({"validated_at_tokens": P, "logits_equal_to_full_recompute": bool(np.allclose(full, cont, atol=1e-3))}, wall, est)


def default_providers() -> list[Provider]:
    return [ComputeProvider(), FleetProvider(), MemoryProvider(), RuntimeProvider(), QuantumProvider(), KvProvider()]

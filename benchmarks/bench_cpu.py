"""TEST 2 — CPU: local vs optimised vs parallel vs distributed vs remote, with energy and cost.

Method: same Mandelbrot checksum computed by every strategy; a strategy only counts if its
result equals the reference. JIT compilation is done before timing and reported separately.
The "remote"/"distributed" strategies use a worker PROCESS ON THIS MACHINE over loopback:
they measure protocol overhead, not the benefit of a second computer.
"""
from __future__ import annotations

import time

from common import save
from spatial.compute import detect_node, limitations
from spatial.compute.cost import CostModel
from spatial.compute.scheduler import ComputeScheduler
from spatial.compute.worker import LocalWorkerProcess
from spatial.core import energy
from spatial.core.ledger import Ledger


def main():
    node = detect_node()
    idle = energy.idle_watts(5.0)
    print("idle machine power (W):", idle)
    cm = CostModel()
    out = {"idle_watts": idle, "limitations": limitations(node), "experiments": []}
    with LocalWorkerProcess() as w:
        c = w.client()
        s = ComputeScheduler(node, Ledger(), c)
        t0 = time.perf_counter()
        s.warmup()
        out["jit_warmup_s"] = time.perf_counter() - t0
        fast_only = {"local_python", "local_numpy"}
        slow_only = {x.name for x in s.mandel_strategies()} - fast_only
        # fast strategies first (cool CPU), repeated; the slow pure-Python reference last, once
        plans = [
            ("mandel_small_fast_strategies", {"n": 700, "iters": 300}, fast_only, 5),
            ("mandel_large_fast_strategies", {"n": 4000, "iters": 300}, fast_only, 3),
            ("mandel_small_slow_references", {"n": 700, "iters": 300}, slow_only, 1),
        ]
        for name, params, skip, repeat in plans:
            runs: dict[str, list] = {}
            for _ in range(repeat):
                for r in s.compare(name, params, s.mandel_strategies(), skip=skip):
                    runs.setdefault(r.strategy, []).append(r)
            rows = []
            for strat, rs in runs.items():
                rs_ok = [r for r in rs if r.ok]
                if not rs_ok:
                    rows.append({"strategy": strat, "ok": False, "notes": rs[0].notes})
                    continue
                best = sorted(rs_ok, key=lambda r: r.wall_s)[len(rs_ok) // 2]     # median run
                loc = cm.local(best.wall_s, best.energy_j, None)   # gauge too coarse for marginal energy
                rows.append({
                    "strategy": strat, "kind": best.metrics["kind"], "ok": True,
                    "wall_s": best.wall_s, "all_wall_s": [r.wall_s for r in rs_ok],
                    "cpu_s": best.cpu_s, "cpu_utilisation": best.cpu_s / best.wall_s if best.wall_s else None,
                    "energy_j_machine": best.energy_j, "mean_watts": best.metrics.get("mean_watts_machine"),
                    "power_gauge_static": best.metrics.get("power_gauge_static"), "energy_usd_upper_bound": loc["energy_usd"],
                    "matches_reference": best.metrics["matches_reference"], "notes": best.notes})
            base = next((r for r in rows if r["strategy"] == ("local_python" if "local_python" in runs else "local_numba_jit")), None)
            for r in rows:
                if r.get("ok") and base:
                    r["speedup_vs_" + base["strategy"]] = base["wall_s"] / r["wall_s"]
            ok_rows = [r for r in rows if r.get("ok")]
            fastest = min(ok_rows, key=lambda r: r["wall_s"])
            cloud = {k: cm.cloud(k, fastest["wall_s"], speed_ratio=sr, result_bytes=64, startup_s=0)
                     for k, sr in (("aws_c7i_large", 1.5), ("aws_c7i_4xlarge", 12.0))}
            out["experiments"].append({"name": name, "params": params, "repeat": repeat, "rows": rows,
                                       "fastest": fastest["strategy"],
                                       "cloud_estimates_for_fastest": cloud,
                                       "cloud_note": "ESTIMATES: speed ratios are assumptions, prices are unverified list prices"})
            for r in rows:
                print(name, r["strategy"], r.get("wall_s"), r.get("energy_j_machine"))
        c.close()
        s.close()
    out["energy_note"] = ("energy_j_machine = last battery-gauge reading x duration (whole machine, screen "
                          "included). The gauge did not change between idle and load, so marginal energy "
                          "per strategy is NOT resolved; treat energy as proportional to wall time.")
    save("cpu", out)


if __name__ == "__main__":
    main()

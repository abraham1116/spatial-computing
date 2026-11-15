"""TEST — is the single objective's decision a GOOD decision?

For each case the planner chooses from its estimates; then EVERY feasible option is run for real and
timed. We report whether the planner's choice was the truly fastest (equal cost rate, so cheapest = fastest
on one machine), how much time a wrong choice would have cost (regret), and the estimate error.
The cases are picked so that the best option CHANGES with size (small jobs: JIT overhead and start-up
dominate; large jobs: raw speed dominates; small circuits: NumPy; larger: Aer).
"""
from __future__ import annotations

import os
import statistics
import tempfile
import time

from common import save
from spatial.core.ledger import Ledger
from spatial.unified import Job, Objective, Planner

LAYERED = """
quantum layered(n, depth) {
    qubit q[n];
    for d in 0..depth {
        for i in 0..n { ry(0.1 * (i + 1) + 0.37 * d) q[i]; rz(0.2 * (d + 1)) q[i]; }
        for i in 0..n - 1 { cx q[i], q[i + 1]; }
    }
}
main { }
"""


def timed(fn, reps=3):
    best = float("inf")
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def main():
    pl = Planner(ledger=Ledger(os.path.join(tempfile.mkdtemp(), "plan.jsonl")))
    held_out = os.environ.get("HELDOUT") == "1"       # sizes and parameters never used while tuning the planner
    fabric = os.environ.get("FABRIC") == "1"          # one job, several devices (CPU / Metal GPU / NVIDIA GPU when present)
    if fabric:
        cases = [("mandel_f32", Job.compute("mandel_f32", n=n, iters=iters)) for n, iters in
                 ((32, 100), (128, 100), (300, 150), (600, 150), (1024, 200), (2048, 200), (3000, 300))]
    elif held_out:
        cases = ([("mandel", Job.compute("mandel", n=n, iters=iters)) for n, iters in ((24, 100), (96, 250), (250, 100), (600, 60))]
                 + [("heat", Job.compute("heat", n=n, steps=steps)) for n, steps in ((40, 100), (90, 300), (160, 150))]
                 + [("quantum", Job.quantum(LAYERED, "layered", [q, 2], 500)) for q in (6, 12, 15, 17, 19)])
    else:
        cases = ([("mandel", Job.compute("mandel", n=n, iters=150)) for n in (16, 48, 150, 400)]
                 + [("heat", Job.compute("heat", n=n, steps=200)) for n in (20, 60, 120)]
                 + [("quantum", Job.quantum(LAYERED, "layered", [q, 3], 1000)) for q in (4, 10, 14, 16, 18, 20)])
    rows = []
    for fam, job in cases:
        plan = pl.plan(job)
        measured = {}
        for o in plan.options:
            if o.feasible and o.run:
                o.run()                                              # warm-up outside the timing
                measured[o.name] = timed(o.run, 2 if fam == "mandel" and job.spec["params"]["n"] >= 150 else 3)
        truth = min(measured, key=measured.get)
        chosen = plan.chosen.name
        rows.append({"family": fam, "job": {k: v for k, v in job.spec.items() if k != "source"} if fam != "quantum" else f"{job.spec['args'][0]} qubits",
                     "chosen": chosen, "truly_fastest": truth, "correct": chosen == truth,
                     "regret": measured[chosen] / measured[truth], "estimate_error_pct": 100 * (plan.chosen.est_time_s - measured[chosen]) / measured[chosen],
                     "measured_s": measured, "estimated_s": {o.name: o.est_time_s for o in plan.options if o.feasible}})
        print(f"{fam:<8}{str(rows[-1]['job'])[:34]:<36}chose {chosen:<14} fastest {truth:<14} regret {rows[-1]['regret']:.2f}x  err {rows[-1]['estimate_error_pct']:+.0f}%", flush=True)
    ok = sum(r["correct"] for r in rows)
    out = {"cases": len(rows), "correct": ok, "accuracy": ok / len(rows), "mean_regret": statistics.mean(r["regret"] for r in rows),
           "max_regret": max(r["regret"] for r in rows),
           "median_abs_estimate_error_pct": statistics.median(abs(r["estimate_error_pct"]) for r in rows), "rows": rows,
           "note": "one machine, equal price per hour for every option, so cheapest = fastest"}
    out["held_out"], out["fabric"] = held_out, fabric
    save("unified_fabric" if fabric else ("unified_heldout" if held_out else "unified"), out)
    print({k: round(v, 3) if isinstance(v, float) else v for k, v in out.items() if k != "rows"})


if __name__ == "__main__":
    main()

"""D6 — re-verify the claims of the saved benchmark results on the machine you run this on.

Absolute speeds depend on the machine, so each check tests a PROPERTY the published numbers rely on
(correct results, a decision within a regret bound, no errors at a load) and prints the saved figure beside
the fresh one. Exit code 1 if any property fails. Used by .github/workflows/verify.yml (weekly) and by hand:
    python benchmarks/verify.py            # about 3 minutes
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).parent))
RES = ROOT / "benchmarks" / "results"
rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str):
    rows.append((name, ok, detail)); print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)


def saved(name):
    try:
        return json.loads((RES / f"{name}.json").read_text())
    except FileNotFoundError:
        return {}


def interconnect():
    from spatial.interconnect import launch, tasks
    from spatial.interconnect.model import choose_calibrated, fit_algo, is_pow2
    n = 4
    errs = launch(n, tasks.check_allreduce, "ring", 4096, timeout_s=120)
    errs += launch(n, tasks.check_allreduce, "halving_doubling", 4096, timeout_s=120)
    errs += launch(n, tasks.check_allreduce, "tree", 4096, timeout_s=120)
    check("interconnect: all three all-reduce algorithms give the exact sum", max(errs) < 1e-3, f"worst deviation {max(errs):.1e}")
    sizes = [1 << 8, 1 << 14, 1 << 18, 1 << 20]
    res = launch(n, tasks.bench_all, sizes, ("ring", "halving_doubling", "tree"), 3, timeout_s=300)[0]
    algos = ("ring", "halving_doubling", "tree")
    regrets = []
    for k, r in enumerate(res["rows"]):                      # leave one size out, calibrate per algorithm, judge on the held-out size
        fits = {a: fit_algo(a, n, [(q["bytes"], q["measured_s"][a]) for j, q in enumerate(res["rows"]) if j != k]) for a in algos}
        pick, _ = choose_calibrated(n, r["bytes"], fits)
        regrets.append(r["measured_s"][pick] / min(r["measured_s"].values()))
    old = saved("interconnect").get("calibrated_leave_one_size_out_N8", {}).get("mean_regret")
    check("interconnect: calibrated algorithm choice stays within 2x of the best", max(regrets) < 2.0,
          f"max regret {max(regrets):.2f}x, mean {sum(regrets) / len(regrets):.2f}x (saved N=8 mean {old if old is None else round(old, 2)}x)")


def kernels():
    from spatial.kernel.library import collatz, mandelbrot
    from spatial.fabric import metal
    a = collatz.run("cpu", 96, limit=300)
    check("kernels: CPU result equals the plain-Python reference", all(int(a[i, j]) == _ref(i * 96 + j + 1, 300) for i in (0, 31, 95) for j in (0, 17, 95)), "spot checks")
    if metal.available():
        import numpy as np
        check("kernels: integer kernel bit-identical on Metal", np.array_equal(collatz.run("metal", 96, limit=300), a), "n=96")
        check("kernels: Metal shared-memory reduction exact", collatz.reduce("metal", 100, limit=300) == collatz.reduce("cpu", 100, limit=300), "n=100")
    else:
        print("SKIP  kernels on Metal: no Metal device on this machine")
    from spatial.unified import Job, Objective, Planner
    pl, reg = Planner(), []
    from spatial.compute import workloads
    for n, it in ((64, 100), (1024, 200)):
        plan = pl.plan(Job.compute("pk_mandel", n=n, iters=it), Objective())
        real = {}
        for o in plan.options:
            if o.feasible:
                o.run(); best = 1e9
                for _ in range(2):
                    t0 = time.perf_counter(); o.run(); best = min(best, time.perf_counter() - t0)
                real[o.name] = best
        reg.append(real[plan.chosen.name] / min(real.values()))
    check("planner: portable-kernel device choice within 2x of the best", max(reg) < 2.0, f"regrets {[round(r, 2) for r in reg]} (saved mean {saved('kernel').get('mean_regret')})")


def _ref(x, lim):
    k = 0
    while x != 1 and k < lim:
        x = x // 2 if x % 2 == 0 else 3 * x + 1
        x = ((x + 2 ** 31) % 2 ** 32) - 2 ** 31
        k += 1
    return k


def fleet():
    import bench_scale
    r = bench_scale.run(100, seconds=10)
    check("fleet: 100 agents, no errors, report p99 under 100 ms", r["errors"] == 0 and r["report_latency_p99_s"] < 0.1,
          f"errors {r['errors']}, p99 {r['report_latency_p99_s'] * 1e3:.1f} ms (saved 100 agents p99 {saved('scale').get('runs', [{}])[0].get('report_latency_p99_s', 0) * 1e3:.1f} ms)")


def tests():
    import subprocess
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", str(ROOT / "tests" / "test_hardening.py"), str(ROOT / "tests" / "test_quorum.py")],
                       capture_output=True, text=True, cwd=ROOT)
    check("security and quorum tests", r.returncode == 0, (r.stdout.strip().splitlines() or ["?"])[-1])


if __name__ == "__main__":
    for step in (interconnect, kernels, fleet, tests):
        try:
            step()
        except Exception as e:                               # a crash is a failure, not a skip
            check(step.__name__, False, f"{type(e).__name__}: {e}")
    bad = [n for n, ok, _ in rows if not ok]
    print(f"\n{len(rows) - len(bad)} of {len(rows)} properties hold" + (f"; FAILED: {', '.join(bad)}" if bad else ""))
    sys.exit(1 if bad else 0)

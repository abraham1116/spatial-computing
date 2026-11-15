"""TEST 4 — SOFTWARE RUNTIME.

One C program is built for four targets (Mach-O, Linux ELF, Windows PE, WASM). The Runtime
Engine inspects each binary, plans a route and executes it. The checksum printed by the
program must equal the Python reference in every environment.

Reference solutions (Docker Desktop, UTM, Parallels, CrossOver) are NOT installed on this
Mac, so no head-to-head comparison is made; only native execution is used as the baseline.
"""
from __future__ import annotations

import tempfile
import time

from common import ROOT, med, save
from spatial.compute import workloads
from spatial.runtime import execute, inspect, plan, toolchain
from spatial.runtime.envs import IsolatedEnv, detect_interpreters

N, ITERS = "1500", "300"


def main():
    src, build = str(ROOT / "benchmarks/src/bench.c"), str(ROOT / "benchmarks/build")
    t0 = time.perf_counter()
    bins = {t: ROOT / "benchmarks/build" / toolchain.TARGETS[t][1] for t in toolchain.TARGETS}
    if not all(p.exists() for p in bins.values()):
        bins = toolchain.build_all(src, build)
    build_s = time.perf_counter() - t0
    ref = workloads.mandel_numba(int(N), int(ITERS))
    out = {"reference_checksum": ref, "build_s": build_s, "params": {"n": N, "iters": ITERS}, "artifacts": [], "runs": []}
    for t, p in bins.items():
        a = inspect(str(p))
        out["artifacts"].append({"target": t, "file": p.name, "bytes": p.stat().st_size, "format": a.format,
                                 "os": a.os, "arch": a.arch,
                                 "routes": [{"name": r.name, "feasible": r.feasible, "reason": r.reason,
                                             "isolation": r.isolation} for r in plan(a)]})
    cases = [("macos-x86_64", "native", 3), ("wasm32-wasi", "wasm-node-wasi", 3),
             ("linux-x86_64", "microvm-hvf", 3), ("linux-x86_64", "microvm-tcg", 1),
             ("windows-x86_64", None, 1)]
    native_ms = None
    for target, route, rep in cases:
        walls, app_ms, boots, ok, chk, extra = [], [], [], True, None, {}
        for _ in range(rep):
            e = execute(str(bins[target]), [N, ITERS], route=route, timeout_s=300)
            ok &= e.ok
            extra = e.extra
            if e.ok:
                _, c, ms = e.stdout.split()
                chk = int(c)
                walls.append(e.wall_s)
                app_ms.append(float(ms))
                if e.extra.get("boot_s"):
                    boots.append(e.extra["boot_s"])
        row = {"target": target, "route": route or e.route, "ok": ok}
        if ok:
            row.update(app_ms=med(app_ms), total_wall_s=med(walls), boot_s=med(boots) if boots else None,
                       checksum_ok=chk == ref, startup_overhead_s=med(walls) - med(app_ms) / 1000)
            if route == "native":
                native_ms = row["app_ms"]
            row["slowdown_vs_native"] = row["app_ms"] / native_ms if native_ms else None
        else:
            row["not_runnable"] = extra.get("not_runnable") or extra
        out["runs"].append(row)
        print(row)
    # dependency management: isolated environment creation
    with tempfile.TemporaryDirectory(prefix="spatial-env-") as td:
        env = IsolatedEnv(td + "/env")
        t = env.create(["tomli==2.0.1"])
        r = env.run("import tomli, sys; print(tomli.__name__, sys.version_info[:2])")
        out["isolated_env"] = {"create_and_install_s": t, "ok": r.returncode == 0, "stdout": r.stdout.strip()}
        env.destroy()
    out["interpreters"] = detect_interpreters()
    print(out["isolated_env"])
    save("runtime", out)


if __name__ == "__main__":
    main()

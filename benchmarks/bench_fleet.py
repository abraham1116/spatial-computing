"""TEST — the fleet end to end with REAL processes: a hub, N agents, and the CLI as the operator.

Scenario A: 1 agent runs 12 tasks.  Scenario B: 3 agents + the hub place the same 12 tasks.
Everything runs on this one machine over loopback, so the speed-up is bounded by its CPU cores
(2 here); the point is correctness of the whole chain (identity, scopes, placement, results,
recommendations), not a scale claim.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from common import ROOT, save
from spatial.compute import workloads

PY = sys.executable
N_TASKS, PARAMS = 12, {"n": 1400, "iters": 300}


def cli(*args, input_text=None):
    r = subprocess.run([PY, "-m", "spatial.cli", *args], capture_output=True, text=True, cwd=ROOT, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"spatial {' '.join(args)} failed: {r.stderr[-400:]}")
    return r.stdout.strip()


def scenario(n_agents: int, tmp: Path) -> dict:
    master, audit, dlog = tmp / f"master{n_agents}.key", tmp / f"audit{n_agents}.jsonl", tmp / f"decisions{n_agents}.jsonl"
    cli("token", "init", "--master-key-file", str(master))
    hub = subprocess.Popen([PY, "-m", "spatial.fleet.hub", "--master-key-file", str(master), "--audit-log", str(audit),
                            "--decision-log", str(dlog)], cwd=ROOT, stdout=subprocess.PIPE, text=True)
    port = int(hub.stdout.readline().split()[1])
    addr = f"127.0.0.1:{port}"

    def token(name, scopes):
        p = tmp / f"{name}.tok"
        p.write_text(cli("token", "issue", "--master-key-file", str(master), "--name", name, "--scopes", scopes, "--ttl", "3600"))
        os.chmod(p, 0o600)
        return str(p)

    ops = token("ops", "fleet:read,fleet:submit")
    agents = [subprocess.Popen([PY, "-m", "spatial.cli", "agent", "--hub", addr, "--token-file",
                                token(f"agent-{i}", "fleet:report,fleet:work"), "--interval", "1", "--usd-per-hour", "1.5"],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for i in range(n_agents)]
    try:
        t = time.time()
        while time.time() - t < 60:                                       # wait until every agent has reported
            if cli("fleet", "status", "--hub", addr, "--token-file", ops, "--window", "30").count("yes") >= n_agents:
                break
            time.sleep(0.5)
        # warm the JIT on every agent so compilation is not timed
        warm = [cli("fleet", "submit", "--hub", addr, "--token-file", ops, "--workload", "mandel_numba",
                    "--params", json.dumps({"n": 8, "iters": 8})) for _ in range(n_agents * 2)]
        for tid in warm:
            while "done" not in cli("fleet", "result", "--hub", addr, "--token-file", ops, "--task-id", tid):
                time.sleep(0.2)
        t0 = time.perf_counter()
        ids = [cli("fleet", "submit", "--hub", addr, "--token-file", ops, "--workload", "mandel_numba",
                   "--params", json.dumps(PARAMS)) for _ in range(N_TASKS)]
        sample_status = sample_advise = None
        results = {}
        while len(results) < N_TASKS:
            for tid in ids:
                if tid in results:
                    continue
                out = cli("fleet", "result", "--hub", addr, "--token-file", ops, "--task-id", tid)
                if "'state': 'done'" in out:
                    results[tid] = eval(out, {"__builtins__": {}})            # our own CLI's dict repr
            if len(results) >= 3 and sample_status is None:
                sample_status = cli("fleet", "status", "--hub", addr, "--token-file", ops, "--window", "6")
                sample_advise = cli("fleet", "advise", "--hub", addr, "--token-file", ops, "--window", "6")
            time.sleep(0.2)
        wall = time.perf_counter() - t0
        ref = workloads.mandel_numba(**PARAMS)
        per_node: dict[str, int] = {}
        for r in results.values():
            per_node[r["node"]] = per_node.get(r["node"], 0) + 1
        advise = sample_advise
        return {"agents": n_agents, "tasks": N_TASKS, "wall_s": wall, "tasks_per_node": per_node,
                "all_results_equal_reference": all(r["result"] == ref for r in results.values()),
                "status_midway": sample_status, "advise_midway": advise, "advise_after": cli("fleet", "advise", "--hub", addr, "--token-file", ops, "--window", "20")}
    finally:
        for a in agents:
            a.terminate()
        hub.terminate()
        from spatial.core.ledger import Ledger
        for a in agents + [hub]:
            try:
                a.wait(timeout=5)
            except subprocess.TimeoutExpired:
                a.kill()
        out_chain = {"audit_chain_ok": Ledger(audit).verify()[0], "decision_rows": len(Ledger(dlog).rows("decision"))}
        globals()["_chain"] = out_chain


def main():
    tmp = Path(tempfile.mkdtemp(prefix="spatial-fleet-"))
    workloads.mandel_numba(8, 8)
    a = scenario(1, tmp)
    ca = dict(_chain)
    b = scenario(3, tmp)
    cb = dict(_chain)
    out = {"params": PARAMS, "one_agent": {**a, **ca}, "three_agents": {**b, **cb},
           "speedup": a["wall_s"] / b["wall_s"], "cores_on_this_machine": os.cpu_count(),
           "note": "agents and hub share one machine; speed-up is bounded by its cores"}
    save("fleet", out)
    print(json.dumps({k: v for k, v in out.items() if k not in ("one_agent", "three_agents")}, indent=1))
    for k in ("one_agent", "three_agents"):
        print(k, {x: y for x, y in out[k].items() if x not in ("status_midway", "advise_midway", "advise_after")})
    print(out["three_agents"]["status_midway"]); print("ADVISE midway:", out["three_agents"]["advise_midway"]); print("ADVISE after:", out["three_agents"]["advise_after"])


if __name__ == "__main__":
    main()

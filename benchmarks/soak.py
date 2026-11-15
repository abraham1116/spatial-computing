"""TEST D2 — soak: hub + 3 agents + a client submitting tasks + a dashboard polling, for N minutes.
Every 10 s the hub and agent processes' RSS, open file descriptors and thread counts are sampled; the report
gives the slope per hour and whether tasks kept completing. One Mac, loopback: this is minutes, not days."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import psutil

from common import save
from spatial.core.protocol import RpcClient
from spatial.fleet.dashboard import Dashboard

PY = sys.executable
ROOT = Path(__file__).resolve().parents[1]


def slope_per_hour(ts, ys):
    if len(ts) < 3:
        return None
    return float(np.polyfit(np.array(ts) / 3600.0, np.array(ys, dtype=float), 1)[0])


def main(minutes: float = 15.0):
    tmp = Path(tempfile.mkdtemp())
    tokf = tmp / "tok"; tokf.write_bytes(b"soak-secret")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    port = 7893
    procs = {"hub": subprocess.Popen([PY, "-m", "spatial.fleet.hub", "--token-file", str(tokf), "--port", str(port), "--state-file", str(tmp / "s.json"), "--max-finished", os.environ.get("SOAK_MAX_FINISHED", "5000"),
                                      "--decision-log", str(tmp / "d.jsonl")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)}
    time.sleep(2)
    for i in range(3):
        procs[f"agent{i}"] = subprocess.Popen([PY, "-m", "spatial.cli", "agent", "--hub", f"127.0.0.1:{port}", "--token-file", str(tokf), "--name", f"a{i}", "--interval", "1"],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    dash = Dashboard(f"127.0.0.1:{port}", tokf.read_bytes(), interval_s=2.0).start()
    stop = threading.Event()
    submitted, errors = [0], [0]

    def client():
        c = None
        while not stop.is_set():
            try:
                c = c or RpcClient("127.0.0.1", port, tokf.read_bytes(), timeout=30)
                c.call({"op": "submit", "workload": "montecarlo_pi", "params": {"samples": 20000}})
                submitted[0] += 1
                if submitted[0] % 20 == 0:                      # also churn connections: open, call, close
                    RpcClient("127.0.0.1", port, tokf.read_bytes(), timeout=30).close()
            except Exception:
                errors[0] += 1; c = None
            stop.wait(0.5)
    threading.Thread(target=client, daemon=True).start()
    samples = {k: {"t": [], "rss": [], "fds": [], "threads": []} for k in procs}
    t0 = time.time()
    try:
        while time.time() - t0 < minutes * 60:
            time.sleep(10)
            for k, p in procs.items():
                try:
                    ps = psutil.Process(p.pid)
                    samples[k]["t"].append(time.time() - t0); samples[k]["rss"].append(ps.memory_info().rss / 2 ** 20)
                    samples[k]["fds"].append(ps.num_fds()); samples[k]["threads"].append(ps.num_threads())
                except psutil.Error:
                    pass
        c = RpcClient("127.0.0.1", port, tokf.read_bytes())
        q = c.call({"op": "queue"})[0]["counts"]
    finally:
        stop.set(); dash.stop()
        for p in procs.values():
            p.kill()
    half = lambda v: v[len(v) // 4:]                           # ignore the first quarter: start-up growth
    out = {"minutes": minutes, "tasks_submitted": submitted[0], "client_errors": errors[0], "final_queue_counts": q, "processes": {}}
    for k, s in samples.items():
        out["processes"][k] = {"rss_MiB_start": s["rss"][0], "rss_MiB_end": s["rss"][-1],
                               "rss_MiB_per_hour_after_warmup": slope_per_hour(half(s["t"]), half(s["rss"])),
                               "fds_start": s["fds"][0], "fds_end": s["fds"][-1], "threads_start": s["threads"][0], "threads_end": s["threads"][-1]}
        print(f"{k:<7} RSS {s['rss'][0]:.0f} -> {s['rss'][-1]:.0f} MiB ({out['processes'][k]['rss_MiB_per_hour_after_warmup']:+.1f} MiB/h after warm-up), "
              f"fds {s['fds'][0]} -> {s['fds'][-1]}, threads {s['threads'][0]} -> {s['threads'][-1]}")
    print(f"submitted {submitted[0]}, errors {errors[0]}, final queue {q}")
    save("soak", out)


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 15.0)

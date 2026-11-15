"""TEST G-2 / D3 — many simulated agents against one hub over the real encrypted protocol.
The hub runs in its own process. The agents are threads of ONE other process, so on this 2-core Mac the
agent side competes with the hub for the CPU and the client-side latency is inflated: read the numbers as
an upper bound on latency and a lower bound on capacity."""
from __future__ import annotations

import multiprocessing as mp
import statistics
import threading
import time

import psutil

from common import save
from spatial.core.protocol import RpcClient

TOKEN = b"s" * 32
GB = 2 ** 30


def hub_proc(q, stop):
    from spatial.fleet.hub import serve_hub
    srv, hub = serve_hub(TOKEN, max_connections=4096)
    srv.start()
    q.put((srv.port, __import__("os").getpid()))
    stop.wait()
    srv.stop()


def run(n_agents: int, seconds: float = 20, interval: float = 2.0) -> dict:
    ctx = mp.get_context("spawn")
    q, stop = ctx.Queue(), ctx.Event()
    p = ctx.Process(target=hub_proc, args=(q, stop)); p.start()
    port, pid = q.get(timeout=60)
    hub_ps = psutil.Process(pid)
    lat, errors, done, kinds = [], [0], threading.Event(), {}
    lock = threading.Lock()
    clients = []

    def agent(i):
        try:
            c = RpcClient("127.0.0.1", port, TOKEN, timeout=60)
        except Exception as e:
            with lock: errors[0] += 1; kinds["connect " + type(e).__name__] = kinds.get("connect " + type(e).__name__, 0) + 1
            return
        clients.append(c)
        m = {"cpu_percent": 20 + i % 60, "cpu_count": 4, "load1": 1.0, "ram_total": 16 * GB, "ram_available": 8 * GB,
             "swap_used": 0, "memory_pressure": "normal", "gpus": []}
        nxt = time.time() + (i % 100) / 100 * interval
        while not done.is_set():
            time.sleep(max(0, nxt - time.time())); nxt += interval
            if done.is_set():
                break                      # do not count calls that race with the shutdown
            t0 = time.perf_counter()
            try:
                c.call({"op": "report", "node": f"n{i}", "metrics": {**m, "ts": time.time()}, "usd_per_hour": 1.0})
                with lock: lat.append(time.perf_counter() - t0)
            except Exception as e:
                with lock: errors[0] += 1; kinds[f"{type(e).__name__}: {str(e)[:60]}"] = kinds.get(f"{type(e).__name__}: {str(e)[:60]}", 0) + 1
    ths = [threading.Thread(target=agent, args=(i,), daemon=True) for i in range(n_agents)]
    t0 = time.time()
    for t in ths: t.start()
    time.sleep(seconds)
    ops = RpcClient("127.0.0.1", port, TOKEN)
    q_lat = {}
    for op in ("nodes", "advise"):
        ts = []
        for _ in range(5):
            a = time.perf_counter(); ops.call({"op": op}); ts.append(time.perf_counter() - a)
        q_lat[op] = statistics.median(ts)
    rss = hub_ps.memory_info().rss
    done.set(); wall = time.time() - t0
    time.sleep(0.5)
    stop.set(); p.join(10)
    lat.sort()
    pct = lambda x: lat[min(len(lat) - 1, int(len(lat) * x))] if lat else None
    return {"agents": n_agents, "interval_s": interval, "offered_reports_per_s": n_agents / interval, "reports": len(lat),
            "achieved_reports_per_s": len(lat) / wall, "errors": errors[0], "report_latency_p50_s": pct(0.5),
            "report_latency_p99_s": pct(0.99), "report_latency_max_s": lat[-1] if lat else None,
            "error_kinds": kinds, "status_latency_s": q_lat["nodes"], "advise_latency_s": q_lat["advise"], "hub_rss_MiB": rss / 2 ** 20}


def main():
    out = {"runs": []}
    for n in (100, 300, 1000):
        r = run(n)
        out["runs"].append(r)
        print(f"{n:>5} agents: offered {r['offered_reports_per_s']:.0f}/s achieved {r['achieved_reports_per_s']:.0f}/s errors {r['errors']} "
              f"p50 {r['report_latency_p50_s'] * 1e3:.1f} ms p99 {r['report_latency_p99_s'] * 1e3:.0f} ms status {r['status_latency_s'] * 1e3:.0f} ms "
              f"advise {r['advise_latency_s'] * 1e3:.0f} ms hub RSS {r['hub_rss_MiB']:.0f} MiB {r['error_kinds']}", flush=True)
    save("scale", out)


if __name__ == "__main__":
    main()

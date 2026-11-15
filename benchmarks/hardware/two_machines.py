"""Offload and remote memory between TWO real machines.

On machine B (the remote one), inside the project:
    python3 -c "import os;open('/tmp/spatial.token','wb').write(os.urandom(32))"; chmod 600 /tmp/spatial.token
    spatial serve compute --token-file /tmp/spatial.token --host 0.0.0.0 --port 7701 --allow-remote
    spatial serve memory  --token-file /tmp/spatial.token --host 0.0.0.0 --port 7702 --allow-remote
    (--allow-remote is explicit consent to accept LAN connections: only do it on a network you control.
     Copy /tmp/spatial.token to machine A over a safe channel.)

On machine A:
    python3 benchmarks/hardware/two_machines.py --host <B address> --token-file /tmp/spatial.token

Measures: round-trip time, remote vs local compute for the same workload (result must be identical),
and tiered-memory latency with the far tier on machine B. Real network numbers, not emulated.
"""
import argparse
import json
import socket
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spatial.compute import workloads  # noqa: E402
from spatial.core.protocol import RpcClient  # noqa: E402
from spatial.memory import RemoteBackend, TieredStore  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--compute-port", type=int, default=7701)
    ap.add_argument("--memory-port", type=int, default=7702)
    ap.add_argument("--n", type=int, default=2000)
    a = ap.parse_args()
    token = Path(a.token_file).read_bytes()
    try:
        cc = RpcClient(a.host, a.compute_port, token, timeout=60)
        mc = RpcClient(a.host, a.memory_port, token, timeout=60)
    except OSError as e:
        print(json.dumps({"ok": False, "error": f"cannot reach the remote machine: {e}"}))
        sys.exit(2)
    out = {"remote": a.host, "local_host": socket.gethostname()}
    rtt = []
    for _ in range(50):
        t = time.perf_counter()
        cc.call({"op": "ping"})
        rtt.append((time.perf_counter() - t) * 1e3)
    out["rtt_ms"] = {"median": statistics.median(rtt), "min": min(rtt), "max": max(rtt)}
    workloads.mandel_numba(8, 8)
    t = time.perf_counter()
    local = workloads.mandel_numba(a.n, 300)
    out["local_s"] = time.perf_counter() - t
    cc.call({"op": "run", "workload": "mandel_numba", "params": {"n": 8, "iters": 8}})      # warm the remote JIT
    t = time.perf_counter()
    rh, _ = cc.call({"op": "run", "workload": "mandel_numba", "params": {"n": a.n, "iters": 300}})
    out["remote_total_s"] = time.perf_counter() - t
    out["remote_compute_s"] = rh["wall_s"]
    out["network_overhead_s"] = out["remote_total_s"] - rh["wall_s"]
    out["results_identical"] = rh["result"] == local
    page = 65536
    import numpy as np
    pages = [np.cumsum(np.random.default_rng(i).integers(0, 3, page // 8)).astype("float64").tobytes() for i in range(512)]
    st = TieredStore(8 * page, 8 * page, RemoteBackend(mc, "remote-real-link"), prefetch=0, keep_latencies=True)
    for i, p in enumerate(pages):
        st.put(i, p)
    t = time.perf_counter()
    ok = all(st.get(i) == pages[i] for i in range(512))
    s = st.stats()
    out["memory"] = {"pages": 512, "page_bytes": page, "all_correct": ok, "scan_s": time.perf_counter() - t,
                     "far_p50_us": s.get("far_p50_us"), "far_p99_us": s.get("far_p99_us"), "far_hits": s["far_hits"]}
    print(json.dumps(out, indent=1))
    Path("benchmarks/results").mkdir(parents=True, exist_ok=True)
    Path("benchmarks/results/two_machines.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()

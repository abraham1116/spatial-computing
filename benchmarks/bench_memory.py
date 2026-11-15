"""TEST 1 — MEMORY.

A. Real state of the Mac's memory (compressor, swap, pressure).
B. Codec micro-benchmark on three kinds of page content (ratio, MB/s).
C. Tiered store: per-tier access latency and throughput for several far tiers, against an
   all-in-RAM baseline, each configuration in a fresh process to read its peak RSS.
D. Optimisation loop: sequential scan with and without read-ahead.

Far tiers "lan-emulated" and "wan-emulated" add an artificial delay / bandwidth cap to a
loopback page server. They are EMULATIONS used to bound the behaviour of a real link.
Nothing here is extra RAM: T1 costs CPU, T2 costs latency, and both are reported.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import resource
import tempfile
import time

import numpy as np

from common import save
from spatial.compute.monitor import snapshot
from spatial.memory import FileBackend, RemoteBackend, TieredStore
from spatial.memory.pageserver import LocalPageServer
from spatial.memory.tiered import codec

PAGE = 65536


def make_page(i: int, kind: str | None = None) -> bytes:
    """Deterministic page content. kinds: numeric (smooth float64), text (JSON-like), random."""
    rng = np.random.default_rng(i)
    kind = kind or ("numeric", "text", "random", "numeric", "text")[i % 5]     # 40/40/20 mix
    if kind == "numeric":
        base = np.cumsum(rng.integers(0, 3, PAGE // 8)).astype(np.float64)
        return base.tobytes()
    if kind == "text":
        rec = [json.dumps({"id": int(i * 1000 + j), "status": ["ok", "warn", "fail"][int(rng.integers(3))],
                           "value": round(float(rng.random()), 3), "node": f"node-{int(rng.integers(40))}"})
               for j in range(900)]
        return ("\n".join(rec).encode() + b" " * PAGE)[:PAGE]
    return rng.bytes(PAGE)


def codec_bench() -> list[dict]:
    rows = []
    for kind in ("numeric", "text", "random"):
        pages = [make_page(i, kind) for i in range(64)]
        raw = sum(map(len, pages))
        for name in ("lz4", "zlib1"):
            c = codec(name)
            t0 = time.perf_counter()
            blobs = [c.enc(p) for p in pages]
            te = time.perf_counter() - t0
            t0 = time.perf_counter()
            for b in blobs:
                c.dec(b)
            td = time.perf_counter() - t0
            comp = sum(map(len, blobs))
            rows.append({"content": kind, "codec": name, "ratio": raw / comp,
                         "compress_MBps": raw / 1e6 / te, "decompress_MBps": raw / 1e6 / td})
    return rows


def run_config(cfg: dict) -> dict:
    """Executed in a fresh process."""
    npages, accesses = cfg["npages"], cfg["accesses"]
    srv = None
    far = None
    tmp = None
    if cfg["far"] == "ssd-file":
        tmp = tempfile.mkdtemp(prefix="spatial-far-")
        far = FileBackend(os.path.join(tmp, "far.bin"))
    elif cfg["far"] in ("loopback-ram", "lan-emulated", "wan-emulated"):
        delay, mbps = {"loopback-ram": (0, 0), "lan-emulated": (0.2, 1000), "wan-emulated": (20, 100)}[cfg["far"]]
        srv = LocalPageServer(delay_ms=delay, mbps=mbps)
        far = RemoteBackend(srv.client(), cfg["far"])
    st = TieredStore(cfg["hot_mb"] << 20, cfg["comp_mb"] << 20, far, codec_name=cfg.get("codec", "lz4"),
                     prefetch=cfg.get("prefetch", 0), keep_latencies=True,
                     keep_far_copy=cfg.get("keep_far_copy", False))
    t = os.times()
    cpu0 = t.user + t.system
    t0 = time.perf_counter()
    for i in range(npages):
        st.put(i, make_page(i))
    load_s = time.perf_counter() - t0
    rng = np.random.default_rng(42)
    if cfg["pattern"] == "zipf":
        keys = (rng.zipf(1.2, accesses) - 1) % npages
        keys = (keys * 2654435761) % npages          # spread hot keys over the key space
    elif cfg["pattern"] == "uniform":
        keys = rng.integers(0, npages, accesses)
    else:
        keys = np.arange(accesses) % npages
    # reset latency samples so the load phase does not pollute access statistics
    for k in st.lat:
        st.lat[k].clear()
    for s_ in st.st.values():
        s_.hits = 0
        s_.ns = 0
    st.far_writes = st.clean_evictions = 0
    check = 0
    t0 = time.perf_counter()
    for k in keys:
        check ^= st.get(int(k))[0]
    acc_s = time.perf_counter() - t0
    t = os.times()
    stats = st.stats()
    stats.update({
        "config": cfg, "load_s": load_s, "access_s": acc_s,
        "accesses_per_s": accesses / acc_s, "throughput_MBps": accesses * PAGE / 1e6 / acc_s,
        "mean_access_us": acc_s / accesses * 1e6, "cpu_s": t.user + t.system - cpu0,
        "peak_rss_MB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6,
        "logical_MB": stats["logical_bytes"] / 1e6, "local_ram_MB": stats["local_ram_bytes"] / 1e6,
        "checksum": check})
    st.close()
    if srv:
        srv.stop()
    if tmp:
        try:
            os.rmdir(tmp)
        except OSError:
            pass
    return stats


def main():
    out = {"page_bytes": PAGE, "system_memory": snapshot(), "codecs": codec_bench()}
    for r in out["codecs"]:
        print("codec", r)
    N = 2048           # 128 MiB logical
    base = {"npages": N, "accesses": 20000, "pattern": "zipf", "hot_mb": 16, "comp_mb": 16}
    configs = [
        {**base, "label": "baseline all-in-RAM", "far": None, "hot_mb": 256, "comp_mb": 0},
        {**base, "label": "tiered + SSD file", "far": "ssd-file"},
        {**base, "label": "tiered + remote RAM (loopback)", "far": "loopback-ram"},
        {**base, "label": "tiered + remote RAM (LAN emulated 0.2 ms, 1 Gb/s)", "far": "lan-emulated"},
        {**base, "label": "tiered + remote RAM (WAN emulated 20 ms, 100 Mb/s)", "far": "wan-emulated",
         "npages": 512, "accesses": 3000, "hot_mb": 4, "comp_mb": 4},
        {**base, "label": "uniform access, SSD file (worst case for tiering)", "far": "ssd-file", "pattern": "uniform"},
        # optimisation loop: sequential scan, read-ahead off then on
        {**base, "label": "sequential scan LAN, no read-ahead", "far": "lan-emulated", "pattern": "seq",
         "accesses": 2048, "prefetch": 0},
        {**base, "label": "sequential scan LAN, read-ahead 16", "far": "lan-emulated", "pattern": "seq",
         "accesses": 2048, "prefetch": 16},
        {**base, "label": "sequential scan LAN, read-ahead 16 + clean-copy retention", "far": "lan-emulated",
         "pattern": "seq", "accesses": 2048, "prefetch": 16, "keep_far_copy": True},
        {**base, "label": "zipf LAN + clean-copy retention", "far": "lan-emulated", "keep_far_copy": True},
    ]
    rows = []
    ctx = mp.get_context("spawn")
    for cfg in configs:
        with ctx.Pool(1) as pool:
            r = pool.apply(run_config, (cfg,))
        rows.append(r)
        print(f"{cfg['label']:<55} {r['mean_access_us']:>10.1f} us/access  "
              f"hot {r['hot_hit_ratio']:.2f} comp {r['compressed_hit_ratio']:.2f} far {r['far_hit_ratio']:.2f}  "
              f"local RAM {r['local_ram_MB']:.0f}/{r['logical_MB']:.0f} MB  rss {r['peak_rss_MB']:.0f} MB")
    out["tiered"] = rows
    out["system_memory_after"] = snapshot()
    save("memory", out)


if __name__ == "__main__":
    main()

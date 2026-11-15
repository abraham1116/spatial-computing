"""TEST — more data than physical RAM.

Writes LOGICAL_GIB of pages into a TieredStore whose local RAM budget is far smaller than the
data, spilling to an SSD file, then verifies a random sample of pages byte for byte and times
accesses. RAM is not extended: the data lives on disk; the test shows the tiered store stays
correct and bounded in memory at a scale well above the machine's 16 GB.
Needs about LOGICAL_GIB/2 of free disk (pages are compressed). Run: python benchmarks/bench_bigdata.py [GiB]
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time

import numpy as np
import psutil

from common import save
from spatial.memory import FileBackend, TieredStore

PAGE = 1 << 20          # 1 MiB pages


def page(i: int) -> bytes:
    """Deterministic content, regenerable for verification: 50 % compressible numeric, 25 % text-like, 25 % random."""
    rng = np.random.default_rng(i)
    k = i % 4
    if k < 2:
        return np.cumsum(rng.integers(0, 3, PAGE // 8)).astype(np.float64).tobytes()
    if k == 2:
        return (b"record,status=ok,value=%d;" % i * (PAGE // 24 + 1))[:PAGE]
    return rng.bytes(PAGE)


def main():
    gib = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
    n = int(gib * (1 << 30) / PAGE)
    ram = psutil.virtual_memory().total
    d = tempfile.mkdtemp(prefix="spatial-big-")
    far = FileBackend(os.path.join(d, "far.bin"))
    st = TieredStore(hot_bytes=256 << 20, compressed_bytes=256 << 20, far=far, codec_name="lz4", keep_latencies=True)
    proc = psutil.Process()
    peak_rss = 0
    t0 = time.perf_counter()
    for i in range(n):
        st.put(i, page(i))
        if i % 256 == 0:
            peak_rss = max(peak_rss, proc.memory_info().rss)
    load_s = time.perf_counter() - t0
    s0 = st.stats()
    rng = np.random.default_rng(99)
    sample = rng.integers(0, n, 600)
    for k in st.lat:
        st.lat[k].clear()
    t0 = time.perf_counter()
    bad = 0
    for i in sample:
        if st.get(int(i)) != page(int(i)):
            bad += 1
        peak_rss = max(peak_rss, proc.memory_info().rss)
    rand_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    scan = range(0, min(n, 2048))
    for i in scan:
        if hashlib.blake2b(st.get(i), digest_size=8).digest() != hashlib.blake2b(page(i), digest_size=8).digest():
            bad += 1
    scan_s = time.perf_counter() - t0
    s = st.stats()
    far_file = os.path.getsize(os.path.join(d, "far.bin"))
    out = {"logical_GiB": n * PAGE / (1 << 30), "physical_RAM_GiB": ram / (1 << 30),
           "logical_over_RAM": n * PAGE / ram, "page_MiB": PAGE >> 20, "pages": n,
           "local_RAM_budget_MiB": 512, "peak_process_RSS_MiB": peak_rss / (1 << 20),
           "far_file_GiB": far_file / (1 << 30), "load_s": load_s, "load_MBps": n * PAGE / 1e6 / load_s,
           "verified_random_pages": len(sample), "verified_scan_pages": len(scan), "corrupt_pages": bad,
           "random_access_ms_mean": rand_s / len(sample) * 1e3,
           "random_p50_ms": {t: s.get(f"{t}_p50_us", 0) / 1e3 for t in ("hot", "compressed", "far")},
           "random_p99_ms": {t: s.get(f"{t}_p99_us", 0) / 1e3 for t in ("hot", "compressed", "far")},
           "scan_MBps": len(scan) * PAGE / 1e6 / scan_s, "tier_hits": {t: s[f"{t}_hits"] for t in ("hot", "compressed", "far")},
           "compression_ratio": s["compression_ratio"], "local_ram_bytes_accounted": s["local_ram_bytes"]}
    st.close()
    save("bigdata", out)
    print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in out.items()})
    assert bad == 0, "corrupt pages"


if __name__ == "__main__":
    main()

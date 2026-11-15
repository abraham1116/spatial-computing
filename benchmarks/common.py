"""Shared benchmark helpers. Results are written as JSON with the machine context so
every number can be traced to the conditions it was measured in."""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "benchmarks" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

from spatial.compute import detect_node, snapshot  # noqa: E402
from spatial.core import energy  # noqa: E402


def context() -> dict:
    n = detect_node()
    batt = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout.strip().splitlines()
    return {"date": time.strftime("%Y-%m-%d %H:%M:%S %z"), "model": n.attrs["model"], "cpu": n.attrs["cpu_brand"],
            "os": n.os, "arch": n.arch, "power_source": batt[0] if batt else None,
            "battery": batt[1].strip() if len(batt) > 1 else None,
            "energy_measurable": energy.available(), "system_before": snapshot()}


def save(name: str, data: dict) -> Path:
    data = {"context": context(), **data}
    p = RESULTS / f"{name}.json"
    p.write_text(json.dumps(data, indent=1, default=str))
    print(f"[saved] {p}")
    return p


def med(xs):
    return statistics.median(xs)


def timeit(fn, repeat: int = 3):
    """Returns (median seconds, all seconds, last result)."""
    ts, r = [], None
    for _ in range(repeat):
        t0 = time.perf_counter()
        r = fn()
        ts.append(time.perf_counter() - t0)
    return med(ts), ts, r

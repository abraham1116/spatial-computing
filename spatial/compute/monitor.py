"""Resource monitoring: CPU, RAM, macOS compressor and swap, memory pressure."""
from __future__ import annotations

import os
import re
import resource
import subprocess
import sys
import time

import psutil

from ..core import energy
from ..core.model import Measurement

_PRESSURE = {1: "normal", 2: "warning", 4: "critical"}


def vm_stat() -> dict[str, int]:
    """Parsed `vm_stat` in bytes (macOS). Empty dict elsewhere."""
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return {}
    page = int(re.search(r"page size of (\d+)", out).group(1))
    d = {}
    for k, v in re.findall(r'^"?([^":]+)"?:\s+(\d+)\.', out, re.M):
        d[k.strip().lower().replace(" ", "_").replace("-", "_")] = int(v)
    for k in list(d):
        if k.startswith("pages_"):
            d[k + "_bytes"] = d[k] * page
    d["page_size"] = page
    return d


def snapshot() -> dict:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    vs = vm_stat()
    snap = {
        "ts": time.time(),
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "load1": os.getloadavg()[0],
        "ram_total": vm.total, "ram_available": vm.available, "ram_used_percent": vm.percent,
        "swap_used": sw.used, "swap_total": sw.total,
    }
    if vs:
        stored = vs.get("pages_stored_in_compressor_bytes", 0)
        occupied = vs.get("pages_occupied_by_compressor_bytes", 0)
        snap.update({
            "compressor_logical_bytes": stored,          # uncompressed size held by compressor
            "compressor_physical_bytes": occupied,       # RAM actually used to hold it
            "compressor_ratio": round(stored / occupied, 2) if occupied else None,
            "compressor_saved_bytes": stored - occupied,
            "swapins": vs.get("swapins"), "swapouts": vs.get("swapouts"),
        })
    try:
        lvl = int(subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                                 capture_output=True, text=True, timeout=5).stdout.strip())
        snap["memory_pressure"] = _PRESSURE.get(lvl, str(lvl))
    except Exception:
        snap["memory_pressure"] = None
    return snap


def underused(snap: dict) -> list[str]:
    """Flag resources that are idle right now (input for the optimizer)."""
    out = []
    if snap["cpu_percent"] < 25:
        out.append(f"CPU {snap['cpu_percent']:.0f}% busy: {100 - snap['cpu_percent']:.0f}% idle capacity")
    if snap["ram_available"] / snap["ram_total"] > 0.4:
        out.append(f"RAM {snap['ram_available'] / 2**30:.1f} GiB available of {snap['ram_total'] / 2**30:.0f}")
    return out


def _peak_rss() -> int:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r if sys.platform == "darwin" else r * 1024   # bytes on macOS, KiB on Linux


class Measure:
    """Measure a block: wall, CPU (self + waited children), peak RSS, battery energy."""

    def __init__(self, engine: str, experiment: str, strategy: str, power: bool = True):
        self.m = Measurement(engine, experiment, strategy, ok=False, wall_s=0.0)
        self._power = energy.PowerSampler() if power else None

    def __enter__(self) -> Measurement:
        t = os.times()
        self._cpu0 = t.user + t.system + t.children_user + t.children_system
        if self._power:
            self._power.__enter__()
        self._t0 = time.perf_counter()
        return self.m

    def __exit__(self, et, ev, tb):
        self.m.wall_s = time.perf_counter() - self._t0
        if self._power:
            self._power.__exit__(et, ev, tb)
            self.m.energy_j = self._power.joules
            if self._power.mean_watts is not None:
                self.m.metrics["mean_watts_machine"] = round(self._power.mean_watts, 2)
                self.m.metrics["power_gauge_static"] = self._power.static
        t = os.times()
        self.m.cpu_s = t.user + t.system + t.children_user + t.children_system - self._cpu0
        self.m.peak_rss_bytes = _peak_rss()
        if et is None:
            self.m.ok = True
        else:
            self.m.notes = f"{et.__name__}: {ev}"
        return True   # failures are recorded, not raised

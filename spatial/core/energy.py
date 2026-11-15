"""Whole-machine power sampling from the battery gauge (no sudo).

MEASURED LIMITATION (MacBookPro14,1, 2026-11-14): the gauge value exposed by ioreg stayed
constant (32.5 W) for 24 s across idle -> full CPU load -> idle. Its refresh period is far
longer than a benchmark run, so per-run energy from this source is only
"last gauge reading x duration". `PowerSampler.static` flags that case; callers must not
derive marginal (above-idle) energy from it. Proper per-run energy needs `powermetrics`
(root) or an external power meter.

Only valid on battery power: on AC the gauge reports charge current, not system
draw, so `available()` is False and energy is reported as None (never guessed).
The value is the power of the WHOLE machine (screen included), so benchmarks
report it next to an idle baseline.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time


def _read() -> tuple[float, bool] | None:
    """Returns (watts drawn, on_battery) or None when no gauge is present."""
    try:
        out = subprocess.run(["ioreg", "-rn", "AppleSmartBattery"], capture_output=True,
                             text=True, timeout=5).stdout
    except Exception:
        return None
    amp = re.search(r'^\s*"InstantAmperage" = (\d+)', out, re.M)
    volt = re.search(r'^\s*"Voltage" = (\d+)', out, re.M)
    ext = re.search(r'^\s*"ExternalConnected" = (\w+)', out, re.M)
    if not (amp and volt and ext):
        return None
    ma = int(amp.group(1))
    if ma >= 1 << 63:           # gauge exposes a signed value as u64
        ma -= 1 << 64
    watts = abs(ma) / 1000.0 * int(volt.group(1)) / 1000.0
    return watts, ext.group(1) == "No"


def available() -> bool:
    r = _read()
    return bool(r and r[1])


class PowerSampler:
    """Context manager: integrates battery power over the block (trapezoid)."""

    def __init__(self, period_s: float = 0.5):
        self.period = period_s
        self.samples: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._t: threading.Thread | None = None
        self.valid = False

    def _loop(self):
        while not self._stop.is_set():
            r = _read()
            if r is None or not r[1]:
                self.valid = False
                return
            self.samples.append((time.perf_counter(), r[0]))
            self._stop.wait(self.period)

    def __enter__(self):
        self.valid = available()
        if self.valid:
            self._t = threading.Thread(target=self._loop, daemon=True)
            self._t.start()
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.t1 = time.perf_counter()
        self._stop.set()
        if self._t:
            self._t.join(timeout=6)
        return False

    @property
    def mean_watts(self) -> float | None:
        if not self.valid or not self.samples:
            return None
        return sum(w for _, w in self.samples) / len(self.samples)

    @property
    def static(self) -> bool:
        """True when the gauge never changed during the window (reading is stale/coarse)."""
        return len({w for _, w in self.samples}) <= 1

    @property
    def joules(self) -> float | None:
        mw = self.mean_watts
        return None if mw is None else mw * (self.t1 - self.t0)


def idle_watts(seconds: float = 4.0) -> float | None:
    with PowerSampler(0.5) as p:
        time.sleep(seconds)
    return p.mean_watts

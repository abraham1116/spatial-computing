"""Fleet screening: run the same known-answer job on every executor, vote, quarantine the odd one out.

The mechanism large GPU fleets use against silent data corruption (periodic known-answer screening, outlier
against the fleet baseline) and against stragglers (a node much slower than its peers on an identical probe),
reduced to a small, testable, vendor-neutral core. An executor is any callable returning an array: a local
device, a remote node, a rented GPU.

What it does not do: no real GPU fault was ever observed here. The tests inject faults. Real corruption is
data-, voltage- and temperature-dependent (NVIDIA/OCP white paper) and a few known-answer kernels will not
cover that test space; this finds gross or systematic miscomputation and gross slowness, not rare faults.
"""

import hashlib
import statistics
import time
from dataclasses import dataclass

import numpy as np

from .consensus import VerificationError


@dataclass(frozen=True)
class ExecResult:
    name: str
    status: str          # "ok" | "outlier" | "undetermined" | "error"
    seconds: float
    digest: str
    error: str = ""


@dataclass(frozen=True)
class ScreenReport:
    results: tuple
    majority: str | None
    outliers: tuple
    errors: tuple
    stragglers: tuple
    reason: str

    @property
    def healthy(self) -> bool:
        return self.majority is not None and not (self.outliers or self.errors or self.stragglers)


def _digest(arr) -> str:
    a = np.ascontiguousarray(arr)
    h = hashlib.sha256()
    h.update(str((a.shape, a.dtype.str)).encode())
    h.update(a.tobytes())
    return h.hexdigest()


def screen(executors: dict, *, clock=time.perf_counter, straggler_factor: float = 2.0,
           straggler_min_gap_s: float = 0.05) -> ScreenReport:
    """Run every executor once and compare. Needs 2+ executors; 3+ to say WHICH one is wrong (with two that
    disagree, nobody can tell). A majority must hold strictly more than half of the executors that ran."""
    if len(executors) < 2:
        raise VerificationError("need at least 2 executors to screen")
    raw = []
    for name, fn in executors.items():
        t0 = clock()
        try:
            digest, err = _digest(np.asarray(fn())), ""
        except Exception as e:                                # a broken executor is a finding, not a crash
            digest, err = "", f"{type(e).__name__}: {e}"
        raw.append((name, digest, clock() - t0, err))
    oks = [r for r in raw if not r[3]]
    counts: dict = {}
    for _, d, _, _ in oks:
        counts[d] = counts.get(d, 0) + 1
    majority = None
    if counts:
        top, c = max(counts.items(), key=lambda kv: kv[1])
        if c >= 2 and c > len(oks) / 2:
            majority = top
    results, outliers, errors = [], [], []
    for name, d, s, err in raw:
        if err:
            status = "error"
            errors.append(name)
        elif majority is None:
            status = "ok" if len(counts) == 1 else "undetermined"
        elif d == majority:
            status = "ok"
        else:
            status = "outlier"
            outliers.append(name)
        results.append(ExecResult(name, status, s, d, err))
    stragglers = []
    if len(oks) >= 3:
        med = statistics.median(s for _, _, s, _ in oks)
        stragglers = [n for n, _, s, _ in oks if s > straggler_factor * med and s - med >= straggler_min_gap_s]
    if not oks:
        reason = "every executor failed"
    elif majority is None and len(counts) > 1:
        reason = ("results disagree and no majority exists: with only two executors nobody can tell which is wrong"
                  if len(oks) == 2 else "results disagree and no majority exists")
    elif outliers:
        reason = f"outlier(s) against a {counts[majority]}-of-{len(oks)} majority: {', '.join(outliers)}"
    elif errors:
        reason = f"executor(s) failed: {', '.join(errors)}"
    elif stragglers:
        reason = f"all agree, but slow against the median: {', '.join(stragglers)}"
    else:
        reason = f"all {len(oks)} executors agree"
    return ScreenReport(tuple(results), majority, tuple(outliers), tuple(errors), tuple(stragglers), reason)


def kernel_executors(kernel, devices, n: int, **params) -> dict:
    """One executor per entry of `devices`; repeated names get a #index suffix. Kernel runs are warmed up once
    (JIT/compile) so the straggler check does not measure compilation."""
    for d in dict.fromkeys(devices):
        try:
            kernel.run(d, 8, **params)
        except Exception:
            pass                                              # surfaces as an error result in the real run
    out = {}
    for i, d in enumerate(devices):
        out[d if list(devices).count(d) == 1 else f"{d}#{i}"] = (lambda d=d: kernel.run(d, n, **params))
    return out


def screen_kernel(kernel, devices, n: int, **params) -> ScreenReport:
    return screen(kernel_executors(kernel, devices, n, **params))

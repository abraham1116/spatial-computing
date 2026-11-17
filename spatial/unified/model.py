"""The single objective and the shared vocabulary of the planner.

OBJECTIVE (the same for every engine): get the job done correctly at the lowest cost in dollars,
within the constraints the caller states (deadline, RAM, isolation, hardware), and PROVE it:
every executed plan records the estimate next to what really happened, and the estimates of the
next plans are corrected by that history.

Costs are computed from prices the caller gives (or the defaults below, which are assumptions).
Nothing here invents a price for a service the caller has not priced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class PlanError(Exception):
    """No option satisfies the objective; the message lists why each one was rejected."""


@dataclass
class Prices:
    # Default = a 2017 laptop amortised over 4 years at 8 h/day plus 32.5 W of electricity at 0.17 $/kWh.
    # It is an ASSUMPTION: set the real figure for your machines.
    local_usd_per_hour: float = 0.134
    ram_usd_gb_hour: float = 0.0          # cost of holding a GB in RAM for an hour (0 = not charged)
    storage_usd_gb_hour: float = 0.0      # same for SSD/object storage
    device_usd_h: dict = field(default_factory=dict)   # price per hour of a specific device/variant, e.g. {"gpu_cuda": 1.2}


@dataclass
class Objective:
    minimize: str = "cost"                # "cost" (default, the one objective) or "time" (tie-break reversed)
    deadline_s: float | None = None
    max_ram_bytes: int | None = None
    require_isolation: bool = False       # binaries: only routes that isolate the program from the host
    allow_remote: bool = True             # fleet nodes

    def __post_init__(self):
        if self.minimize not in ("cost", "time"):
            raise ValueError("minimize must be 'cost' or 'time'")


@dataclass
class Job:
    kind: str                              # compute | binary | dataset | kv
    spec: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def compute(cls, family: str, **params) -> "Job":
        """A numerical job from a registered family (mandel, heat, nbody, hologram, option, ode)."""
        return cls("compute", {"family": family, "params": params})

    @classmethod
    def binary(cls, path: str, args: list[str] | None = None, est_native_s: float = 1.0) -> "Job":
        return cls("binary", {"path": path, "args": args or [], "est_native_s": est_native_s})

    @classmethod
    def dataset(cls, total_bytes: int, accesses: int, locality: float = 0.8, hot_fraction: float = 0.2,
                page_bytes: int = 65536) -> "Job":
        """Keep `total_bytes` addressable and touch it `accesses` times; `locality` of the accesses
        go to the hottest `hot_fraction` of the data."""
        return cls("dataset", {"total_bytes": int(total_bytes), "accesses": int(accesses), "locality": locality,
                               "hot_fraction": hot_fraction, "page_bytes": page_bytes})

    @classmethod
    def kv_cache(cls, prefix_tokens: int, reuse_prob: float, horizon_h: float = 1.0) -> "Job":
        """A cached inference prefix: keep it for later reuse or recompute it when needed (toy model)."""
        return cls("kv", {"prefix_tokens": int(prefix_tokens), "reuse_prob": float(reuse_prob), "horizon_h": horizon_h})

    def label(self) -> str:
        s = {k: v for k, v in self.spec.items() if k != "source"}
        return f"{self.kind} {s}"


@dataclass
class Validated:
    """Returned by options that can only be run at reduced scale (datasets, KV cache): the result plus
    the measured wall time and the time the estimate predicted for that same reduced run."""
    result: Any
    wall_s: float
    est_time_s: float


@dataclass
class Option:
    engine: str
    name: str
    feasible: bool
    reason: str = ""
    est_time_s: float | None = None
    rate_usd_h: float = 0.0               # what the resource costs per hour while this option runs
    fixed_usd: float = 0.0                # costs that do not depend on time
    est_ram_bytes: int | None = None
    isolated: bool | None = None
    basis: str = ""                       # where the time estimate comes from: probe, measured constants, assumption
    run: Callable[[], Any] | None = None
    meta: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.engine}/{self.name}"

    @property
    def est_cost_usd(self) -> float | None:
        if self.est_time_s is None and not self.fixed_usd:
            return None
        return (self.est_time_s or 0.0) / 3600 * self.rate_usd_h + self.fixed_usd

    def reject(self, why: str) -> None:
        self.feasible, self.reason = False, why


@dataclass
class Plan:
    job: Job
    objective: Objective
    prices: Prices
    options: list[Option]                  # ranked: feasible first, by the objective
    chosen: Option | None

    def explain(self) -> str:
        f = lambda v, fmt: "-" if v is None else format(v, fmt)
        rows = [f"job: {self.job.label()}",
                f"objective: minimize {self.objective.minimize}"
                + (f", deadline {self.objective.deadline_s:g} s" if self.objective.deadline_s else "")
                + (f", RAM <= {self.objective.max_ram_bytes / 2**30:.1f} GiB" if self.objective.max_ram_bytes else "")
                + (", isolated" if self.objective.require_isolation else "")
                + f"   (local price {self.prices.local_usd_per_hour:g} $/h)",
                f"{'':3}{'option':<28}{'time_s':>10}{'cost_usd':>12}{'ram_MiB':>9}  {'basis':<22}status"]
        for o in self.options:
            mark = ">>" if o is self.chosen else "  "
            status = "chosen" if o is self.chosen else ("ok" if o.feasible else f"rejected: {o.reason}")
            rows.append(f"{mark} {o.key:<28}{f(o.est_time_s, '.4g'):>10}{f(o.est_cost_usd, '.3g'):>12}"
                        f"{f(None if o.est_ram_bytes is None else o.est_ram_bytes / 2**20, '.0f'):>9}  {o.basis[:22]:<22}{status}")
        return "\n".join(rows)


@dataclass
class Execution:
    option: str
    result: Any
    wall_s: float
    est_time_s: float | None
    time_error_pct: float | None           # (actual - estimate) / estimate
    est_cost_usd: float | None
    actual_cost_usd: float
    calibration_samples: int

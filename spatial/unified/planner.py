"""The planner: every engine proposes options for a job; one function ranks them by the one
objective; executing a plan records estimate versus reality and corrects future estimates."""
from __future__ import annotations

import statistics
import time
from collections import defaultdict, deque

from ..core.ledger import Ledger
from ..core.model import Measurement
from .model import Execution, Job, Objective, Option, Plan, PlanError, Prices, Validated


class Planner:
    def __init__(self, prices: Prices | None = None, ledger: Ledger | None = None, hub=None, providers=None):
        """hub: an RpcClient to a fleet hub with fleet:read and fleet:submit (enables remote options)."""
        from .providers import default_providers
        self.prices = prices or Prices()
        self.ledger = ledger or Ledger()
        self.hub = hub
        self.providers = providers if providers is not None else default_providers()
        self._ratios: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=8))   # actual / estimate, per option

    # ---------------------------------------------------------------- calibration (the learning loop)
    def calibrate(self, kind: str, opt: Option) -> Option:
        """Scale the option's time estimate by the median error of its past executions (needs 2+)."""
        r = self._ratios[(kind, opt.key)]
        if opt.est_time_s is not None and len(r) >= 2:
            opt.est_time_s *= statistics.median(r)
            opt.basis += f"+calibrated({len(r)})"
        return opt

    # ---------------------------------------------------------------- planning
    def plan(self, job: Job, objective: Objective | None = None) -> Plan:
        obj = objective or Objective()
        options: list[Option] = []
        for p in self.providers:
            if job.kind in p.kinds:
                options += p.options(job, obj, self, options)
        for o in options:
            self._apply_constraints(o, obj)
        key = (lambda o: (o.est_cost_usd if o.est_cost_usd is not None else float("inf"),
                          o.est_time_s if o.est_time_s is not None else float("inf"))) if obj.minimize == "cost" else \
              (lambda o: (o.est_time_s if o.est_time_s is not None else float("inf"),
                          o.est_cost_usd if o.est_cost_usd is not None else float("inf")))
        ok = sorted((o for o in options if o.feasible), key=key)
        rest = [o for o in options if not o.feasible]
        plan = Plan(job, obj, self.prices, ok + rest, ok[0] if ok else None)
        if plan.chosen is None:
            raise PlanError("no option satisfies the objective:\n" + plan.explain())
        self.ledger.decide("planner", f"{job.kind}: choose {plan.chosen.key}", f"minimize {obj.minimize}",
                           candidates={o.key: (o.est_cost_usd, o.est_time_s) for o in ok},
                           rejected={o.key: o.reason for o in rest})
        return plan

    @staticmethod
    def _apply_constraints(o: Option, obj: Objective) -> None:
        if not o.feasible:
            return
        if obj.deadline_s is not None:
            if o.est_time_s is None:
                o.reject("duration unknown, cannot promise the deadline")
            elif o.est_time_s > obj.deadline_s:
                o.reject(f"estimated {o.est_time_s:.3g} s exceeds the {obj.deadline_s:g} s deadline")
        if obj.max_ram_bytes is not None and o.est_ram_bytes is not None and o.est_ram_bytes > obj.max_ram_bytes:
            o.reject(f"needs {o.est_ram_bytes / 2**20:.0f} MiB of RAM, limit {obj.max_ram_bytes / 2**20:.0f} MiB")
        if obj.require_isolation and o.isolated is False:
            o.reject("does not isolate the program from the host")

    # ---------------------------------------------------------------- execution + proof
    def execute(self, plan: Plan) -> Execution:
        opt = plan.chosen
        t0 = time.perf_counter()
        ok, err = True, None
        try:
            res = opt.run()
        except Exception as e:
            ok, err, res = False, f"{type(e).__name__}: {e}", None
        wall = time.perf_counter() - t0
        est = opt.est_time_s
        if isinstance(res, Validated):                       # reduced-scale validation: compare like with like
            wall, est, res = res.wall_s, res.est_time_s, res.result
        error = None if (est is None or est <= 0) else (wall - est) / est
        if ok and est and est > 0:
            self._ratios[(plan.job.kind, opt.key)].append(wall / est)
        actual_cost = wall / 3600 * opt.rate_usd_h + opt.fixed_usd
        self.ledger.record(Measurement(
            "planner", plan.job.kind, opt.key, ok, wall, cost_usd=actual_cost,
            metrics={"est_time_s": est, "est_cost_usd": opt.est_cost_usd, "time_error_pct": None if error is None else 100 * error,
                     "basis": opt.basis, "objective": plan.objective.minimize}, notes=err or ""))
        if not ok:
            raise RuntimeError(f"{opt.key} failed: {err}")
        return Execution(opt.key, res, wall, est, None if error is None else 100 * error, opt.est_cost_usd, actual_cost,
                         len(self._ratios[(plan.job.kind, opt.key)]))

    def run(self, job: Job, objective: Objective | None = None) -> tuple[Plan, Execution]:
        """Plan, execute, record: the whole loop in one call."""
        p = self.plan(job, objective)
        return p, self.execute(p)

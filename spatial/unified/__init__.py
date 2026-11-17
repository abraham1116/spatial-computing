"""The unified planner: ONE objective for the whole infrastructure.

    get the job done correctly at the lowest cost in dollars, within the stated constraints,
    and prove it (estimate recorded next to reality; future estimates corrected by that history).

Every engine plugs in through a provider that turns a job into priced options:
compute / simulation / scientific / holographic (numerical families), fleet (nodes), tiered memory
(datasets), runtime (binaries) and the AI cache (KV prefixes).
"""
from .model import Execution, Job, Objective, Option, Plan, PlanError, Prices, Validated  # noqa: F401
from .planner import Planner  # noqa: F401

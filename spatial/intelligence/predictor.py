"""time ~ a * work^b, fitted per strategy by least squares in log-log space."""
from __future__ import annotations

import math
from collections import defaultdict


class PowerLawPredictor:
    def __init__(self):
        self._obs: dict[str, list[tuple[float, float]]] = defaultdict(list)
        self._fit: dict[str, tuple[float, float]] = {}

    def observe(self, strategy: str, work: float, seconds: float) -> None:
        if work > 0 and seconds > 0:
            self._obs[strategy].append((math.log(work), math.log(seconds)))
            self._fit.pop(strategy, None)

    def _params(self, strategy: str) -> tuple[float, float] | None:
        if strategy in self._fit:
            return self._fit[strategy]
        pts = self._obs.get(strategy, [])
        if len({x for x, _ in pts}) < 2:
            return None
        n = len(pts)
        mx = sum(x for x, _ in pts) / n
        my = sum(y for _, y in pts) / n
        sxx = sum((x - mx) ** 2 for x, _ in pts)
        b = sum((x - mx) * (y - my) for x, y in pts) / sxx
        self._fit[strategy] = (my - b * mx, b)
        return self._fit[strategy]

    def predict(self, strategy: str, work: float) -> float | None:
        p = self._params(strategy)
        return None if p is None else math.exp(p[0] + p[1] * math.log(work))

    def best(self, work: float) -> tuple[str, float] | None:
        cands = [(s, self.predict(s, work)) for s in self._obs]
        cands = [(s, t) for s, t in cands if t is not None]
        return min(cands, key=lambda x: x[1]) if cands else None

    @classmethod
    def from_ledger(cls, rows: list[dict], work_of=lambda r: r["metrics"]["params"]["n"] ** 2
                    * r["metrics"]["params"]["iters"]) -> "PowerLawPredictor":
        p = cls()
        for r in rows:
            if r.get("type") == "measurement" and r.get("ok") and "params" in r.get("metrics", {}):
                try:
                    p.observe(r["strategy"], work_of(r), r["wall_s"])
                except (KeyError, TypeError):
                    continue
        return p

"""Append-only JSONL ledger of measurements and decisions (the R&D trace)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .model import Measurement

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "benchmarks" / "results"


class Ledger:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else RESULTS / "ledger.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, m: Measurement) -> Measurement:
        with open(self.path, "a") as f:
            f.write(json.dumps({"type": "measurement", **m.to_dict()}) + "\n")
        return m

    def decide(self, engine: str, decision: str, reason: str, **data) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps({"type": "decision", "ts": time.time(), "engine": engine,
                                "decision": decision, "reason": reason, **data}) + "\n")

    def rows(self, type_: str | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if type_ is None or r.get("type") == type_:
                    out.append(r)
        return out

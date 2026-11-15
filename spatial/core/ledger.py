"""Append-only, hash-chained JSONL ledger of measurements and decisions (the R&D trace).

Every row carries `prev` (hash of the previous row) and `hash` = SHA-256(prev | canonical
JSON of the row). `verify()` detects an edited, removed or reordered row. This is tamper
EVIDENCE, not a signature: someone who can rewrite the whole file can rebuild the chain.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from .model import Measurement

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "benchmarks" / "results"
GENESIS = "0" * 64


def _digest(prev: str, row: dict) -> str:
    body = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev + body).encode()).hexdigest()


class Ledger:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else RESULTS / "ledger.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last = self._tail_hash()

    def _tail_hash(self) -> str:
        last = GENESIS
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    last = json.loads(line).get("hash", last)
        return last

    def _append(self, row: dict) -> None:
        row = json.loads(json.dumps(row, default=str))      # normalise before hashing
        h = _digest(self._last, row)
        with open(self.path, "a") as f:
            f.write(json.dumps({**row, "prev": self._last, "hash": h}) + "\n")
        self._last = h

    def record(self, m: Measurement) -> Measurement:
        self._append({"type": "measurement", **m.to_dict()})
        return m

    def decide(self, engine: str, decision: str, reason: str, **data) -> None:
        self._append({"type": "decision", "ts": time.time(), "engine": engine,
                      "decision": decision, "reason": reason, **data})

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

    def verify(self) -> tuple[bool, int | None]:
        """(True, None) when the chain is intact, else (False, index of the first bad row).
        Rows written before chaining existed (no `hash`) are reported as bad."""
        prev = GENESIS
        for i, r in enumerate(self.rows()):
            h, p = r.pop("hash", None), r.pop("prev", None)
            if h is None or p != prev or _digest(prev, r) != h:
                return False, i
            prev = h
        return True, None

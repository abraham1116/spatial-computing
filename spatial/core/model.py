"""SPATIAL CORE data model shared by every engine.

A Node exposes Resources. A Task declares what it needs. An engine produces a
Measurement for every execution; nothing is claimed without one.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ResourceKind(str, Enum):
    CPU = "cpu"
    GPU = "gpu"
    NPU = "npu"
    RAM = "ram"
    FAR_MEMORY = "far_memory"   # compressed / remote / storage-backed. Never reported as RAM.
    STORAGE = "storage"
    NETWORK = "network"
    QPU = "qpu"
    QSIM = "qsim"               # classical simulator of a quantum device


@dataclass
class Resource:
    kind: ResourceKind
    name: str
    capacity: float               # cores, bytes, qubits, bits/s
    unit: str
    available: float | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Node:
    node_id: str
    hostname: str
    os: str
    arch: str
    resources: list[Resource] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)

    def by_kind(self, kind: ResourceKind) -> list[Resource]:
        return [r for r in self.resources if r.kind == kind]

    def to_dict(self) -> dict:
        d = asdict(self)
        for r in d["resources"]:
            r["kind"] = ResourceKind(r["kind"]).value
        return d


@dataclass
class Task:
    """Unit of work. `workload` names a whitelisted callable; no code is shipped."""
    workload: str
    params: dict[str, Any] = field(default_factory=dict)
    needs: dict[str, float] = field(default_factory=dict)   # e.g. {"ram": 2e9, "cpu": 2}
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class Measurement:
    """One real execution. `ok=False` rows are kept: failures are results."""
    engine: str
    experiment: str
    strategy: str
    ok: bool
    wall_s: float
    cpu_s: float | None = None
    peak_rss_bytes: int | None = None
    energy_j: float | None = None        # None when not measurable (e.g. on AC power)
    cost_usd: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

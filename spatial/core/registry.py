"""Engine registry. Status is a claim that must be backed by `evidence`."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Status(str, Enum):
    OPERATIONAL_PROTOTYPE = "operational-prototype"   # runs, tested, benchmarked on this Mac
    FIRST_COMPONENTS = "first-components"             # some real tested code, not a product
    INTERFACE_ONLY = "interface-only"                 # data model / API only


@dataclass(frozen=True)
class Engine:
    key: str
    name: str
    package: str
    status: Status
    evidence: str     # test or benchmark that justifies the status
    not_done: str     # what is explicitly NOT implemented


ENGINES: list[Engine] = [
    Engine("compute", "Spatial Compute Engine", "spatial.compute", Status.OPERATIONAL_PROTOTYPE,
           "tests/test_compute.py, benchmarks/bench_cpu.py, bench_gpu.py",
           "no real second machine tested (offload and task queue validated over loopback only); no GPU scheduling"),
    Engine("resource", "Spatial Resource Engine (memory tiering)", "spatial.memory",
           Status.OPERATIONAL_PROTOTYPE,
           "tests/test_memory.py, benchmarks/bench_memory.py",
           "user-space object store only; not kernel paging; single writer; no RDMA/CXL hardware"),
    Engine("runtime", "Spatial Runtime Engine", "spatial.runtime", Status.OPERATIONAL_PROTOTYPE,
           "tests/test_runtime.py, benchmarks/bench_runtime.py",
           "Windows apps not demonstrated (no Wine / Windows image); no containers; no GUI streaming"),
    Engine("q", "SPATIAL Q", "spatial.q", Status.OPERATIONAL_PROTOTYPE,
           "tests/test_q.py, benchmarks/bench_q.py",
           "no real QPU executed (OpenQASM 3 and QIR export only); simulator limited by RAM"),
    Engine("ai", "Spatial AI Engine", "spatial.ai", Status.FIRST_COMPONENTS,
           "tests/test_engines.py (toy transformer KV cache: restore equals recompute)",
           "toy NumPy model only; no real LLM, no GPU; placement planner is in the private package"),
    Engine("scientific", "Spatial Scientific & Industrial Engine", "spatial.scientific",
           Status.FIRST_COMPONENTS, "tests/test_domains.py, tests/test_engines.py (validated jobs)",
           "two reference jobs; no domain solvers"),
    Engine("simulation", "Spatial Simulation Engine", "spatial.simulation", Status.FIRST_COMPONENTS,
           "tests/test_domains.py, tests/test_engines.py (heat diffusion, N-body)", "two small solvers; no multiphysics"),
    Engine("intelligence", "Spatial Intelligence Engine", "spatial.intelligence",
           Status.FIRST_COMPONENTS, "tests/test_domains.py, tests/test_engines.py (predictor drives the scheduler)",
           "least-squares runtime model only"),
    Engine("holographic", "Spatial Holographic Engine", "spatial.holographic", Status.FIRST_COMPONENTS,
           "tests/test_engines.py (hologram synthesis + numerical reconstruction)",
           "numerical optics only; no display hardware, no real-time rendering"),
]


def table() -> str:  # noqa: D103
    rows = ["| Engine | Status | Evidence | Not done |", "|---|---|---|---|"]
    for e in ENGINES:
        rows.append(f"| {e.name} | {e.status.value} | {e.evidence} | {e.not_done} |")
    return "\n".join(rows)

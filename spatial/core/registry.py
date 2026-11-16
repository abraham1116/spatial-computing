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
    Engine("fabric", "Virtual accelerator fabric", "spatial.fabric", Status.FIRST_COMPONENTS,
           "tests/test_fabric.py, benchmarks/bench_unified.py (FABRIC=1: 7 of 7 device choices correct)",
           "CPU and Metal GPU tested; the NVIDIA (numba.cuda) path is written and never run on real NVIDIA hardware; one job family; no host-device transfer model"),
    Engine("interconnect", "Virtual interconnect (collectives)", "spatial.interconnect", Status.FIRST_COMPONENTS,
           "tests/test_interconnect.py, benchmarks/bench_interconnect.py (uncalibrated model right 1 of 6; calibrated per algorithm 4 of 6)",
           "N = 4 and 8 processes on one machine over loopback; no real network, RDMA or GPU memory; about 3,000x slower than NVLink 5 (vendor figure); no fault tolerance"),
    Engine("kernel", "Portable kernels", "spatial.kernel", Status.FIRST_COMPONENTS,
           "tests/test_kernel.py, benchmarks/bench_kernel.py (planner right 4 of 6; integer kernel bit-identical CPU vs Metal)",
           "CUDA C and HIP generated, never compiled or run; two kernel shapes (2-D map, whole-grid sum with shared memory), no tiling or tensor cores"),
    Engine("platform", "Console and account service", "spatial.platform", Status.FIRST_COMPONENTS,
           "tests/test_platform.py (14 tests, real hub and agent), a driven browser session",
           "one process with SQLite; no SAML; tax tools are not a compliance engine; e-mail tested against a local SMTP stand-in, payments against a fake Stripe API only"),
    Engine("planner", "Spatial Planner (the one objective)", "spatial.unified", Status.OPERATIONAL_PROTOTYPE,
           "tests/test_unified.py",
           "estimates come from probes and measured constants on one machine; calibration is a median of past ratios; no learned model; fleet and QPU pricing need the caller's prices"),
    Engine("fleet", "Spatial Fleet (agent + hub)", "spatial.fleet", Status.OPERATIONAL_PROTOTYPE,
           "tests/test_fleet.py, benchmarks/bench_fleet.py",
           "validated on one machine (agents on loopback); HA: active/standby for two hubs, majority election (election safety, no replicated log) for three or more, tested on one machine with simulated clocks; dashboard is read-only and local; recommendations are estimates; never applies changes by itself"),
    Engine("runtime", "Spatial Runtime Engine", "spatial.runtime", Status.OPERATIONAL_PROTOTYPE,
           "tests/test_runtime.py, benchmarks/bench_runtime.py",
           "Windows: one console program and one GUI window (Notepad) under Wine, nothing more; containers: static Linux ELF, tested with Docker (Colima) and Podman; Linux GUI apps stream through a container and noVNC (three allow-listed apps)"),
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

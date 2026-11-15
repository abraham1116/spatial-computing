# Limitations (current, English)

This file is kept up to date. The French reports in this folder (`01_`, `05_`, `06_`, `07_`, `10_`, `RESULTATS.fr.md`) were written for v0.1 and are historical: where they disagree with this file or with `CHANGELOG.md`, this file wins.

The list of tests not yet done, with how to run each one, is in [TESTS_NOT_DONE.md](TESTS_NOT_DONE.md).

## Hardware never tested

| Not available | Consequence |
|---|---|
| A second machine | Offload, task queue, remote runner, shared pages and remote memory are validated over loopback or an emulated link only. No capacity gain has been demonstrated. |
| A data-center GPU | `nvidia-smi` detection is parser-tested only. No LLM inference, no GPU scheduling, no cost-per-token measurement. |
| A quantum computer | Six small circuits (Bell, GHZ-3/5, QFT round trip, a layered ansatz) have run on one IBM device on one day ([QPU.md](QPU.md)). No quantum advantage of any kind is shown. Other SPATIAL Q results come from classical simulators. OpenQASM 2/3 and QIR exports are checked by parsers (Qiskit, pyqir), never executed on a QPU. |
| CXL, RDMA, NVMe-oF | Studied on paper only. |
| A dataset larger than RAM | Tested once: 24 GiB logical on a 16 GiB machine, 0 corrupt pages in 2,648 verified, process RSS peak 578 MiB, about 5 ms per random access ([bigdata.json](../benchmarks/results/bigdata.json)). That is disk-backed, not extra RAM, and it was a single run. |
| A power meter | Energy per run is not measured; energy costs are estimates. |

## Measurement

- One reference machine (2017 MacBook Pro, 2 cores). CPU benchmark: 9 and 7 repetitions with min, quartiles and max recorded (interquartile range under 5 % of the median). Other benchmarks: 1 to 5 repetitions. Background load not controlled.
- Results recorded in `benchmarks/results/` date from v0.1 on AC power; on a low battery the same runs were about three times slower.
- LAN/WAN links in the memory benchmark are emulated with `sleep`.
- The GPU benchmark compares against a non-vectorized CPU reference.
- Cloud prices in the cost model are unverified list prices; cloud speed ratios are assumptions.

## Software

| Component | Limit |
|---|---|
| Fabric (devices) | CPU and Metal GPU tested on one Mac; the NVIDIA `numba.cuda` path has never run on real NVIDIA hardware; one job family; no host-device transfer model. See [FABRIC.md](FABRIC.md). |
| Planner (the one objective) | Estimates come from probes and measured constants on one machine; calibration is a median of past ratios; dollar costs use caller-supplied prices (default local price is an assumption); decision quality measured on 25 cases of numerical and quantum-simulation jobs only. See [OBJECTIVE.md](OBJECTIVE.md). |
| Fleet (agent + hub) | Single-process hub with in-memory state (no persistence, no high availability), no dashboard UI, heuristic recommendations, pull-based placement that does not move running work. Validated with 3 agents on one machine only (all three report the same CPU load). See [INFRASTRUCTURE.md](INFRASTRUCTURE.md). |
| Protocol SWP/2 | Encrypted, authenticated and forward-secret; scoped credentials with quotas and a hash-chained audit log. Not independently reviewed; no certificates (the secret is the identity); revocation and usage counters live in server memory; one request at a time per connection. Do not expose to an untrusted network. |
| Tiered memory | Python library used through an API, not transparent paging. Latency is dominated by the interpreter. `SharedPages` gives lost-update-free writes through one server: no consensus, no fault tolerance. |
| Scheduler | Compares strategies by running them; one workload family (Mandelbrot); the `cost` objective uses an assumed price per core-hour. |
| Runtime | Linux route needs QEMU plus two downloaded files; the micro-VM has no network and read-only input files. Windows: one console program verified under Wine, graphical apps untested, Wine never installed automatically. No OCI containers, no remote desktop. The remote runner accepts Linux x86_64 ELF only. |
| SPATIAL Q | Built-in simulator is exact and RAM-bound (about 27 qubits on the reference machine) and slower than Aer beyond ~16 qubits. Noise model: single-qubit depolarizing only. Compiled mode targets Python bytecode, not native code. Optimizer: inverse-pair cancellation, rotation merging and commutation across CX/CZ/CCX (fuzz-tested against the exact state), but no resynthesis. |
| AI engine | A toy NumPy transformer, CPU only. Its restore-versus-recompute timings say nothing about real models or GPUs. |
| Scientific, Simulation, Intelligence | Two validated jobs, two small solvers, one least-squares predictor. |
| Holographic | Numerical optics (hologram synthesis and reconstruction). No display hardware, no real-time rendering. |

## Research

Nothing here is claimed to be novel: published prior art exists for the techniques used. No patent database search has been made.

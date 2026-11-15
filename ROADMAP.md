# Roadmap

What exists is a prototype. This is what is missing, by area. Items marked **needs hardware** cannot be validated on a laptop.

## Cross-cutting
Everything that needs hardware or people is tracked, with how to run it, in [`docs/TESTS_NOT_DONE.md`](docs/TESTS_NOT_DONE.md).

- [ ] Test offload and remote memory between **two real machines** (needs hardware)
- [x] `nvidia-smi` detection in `spatial audit` (v0.3; parser tested, never run on a real NVIDIA GPU)
- [ ] Validation of the scheduler on Linux + NVIDIA (needs hardware)
- [ ] Real per-run energy measurement (`powermetrics` as root, or an external meter)
- [x] Channel encryption (SWP/1: AES-256-GCM, v0.2) and far-page encryption
- [x] Tamper-evident (hash-chained) ledger
- [x] Forward secrecy (ephemeral X25519), scoped credentials with quotas, hash-chained audit log (v0.8)
- [ ] Independent security review, certificate-based identity, signed audit log, durable revocation
- [x] Current limitations in English (`docs/LIMITATIONS.md`, v0.5)
- [ ] Publish to PyPI; English translation of the remaining reports in `docs/`

## Virtual accelerator fabric
- [x] One job on several devices chosen by measured cost: CPU and Metal GPU tested (v0.11); NVIDIA path written, never run
- [ ] First run on a real NVIDIA GPU; more job families; host-to-device transfer model; AMD (ROCm) and remote GPUs

## Planner (one objective)
- [x] Planner with providers for compute, fleet, memory, runtime, SPATIAL Q and the AI cache; probes, constraints, execution, estimate-versus-actual proof, calibration (v0.10)
- [ ] Per-node speed measurement, GPU options, real invoices, a learned runtime model

## Fleet
- [x] Agent and hub: measurement, placement, recommendations, audit (v0.9, validated with 3 agents on one machine)
- [ ] Agents on several real machines; scale tests; hub persistence and high availability
- [ ] Dashboard UI and alerting; automatic application of recommendations (opt-in, with rollback)

## Compute Engine
- [x] Priority task queue across N workers with re-queue on worker failure (v0.2, loopback only)
- [ ] GPU orchestration (CUDA / Metal), local and remote (needs hardware)
- [x] Cost objective in the scheduler (v0.3)
- [ ] Cloud provider integration
- [ ] More workload families than the Mandelbrot reference

## Tiered memory
- [ ] Rewrite hot paths in Rust or C++; keep Python as the decision layer
- [x] Encryption and replication of far pages (v0.2)
- [x] Several writers on shared pages (versioned compare-and-swap, single server, v0.5)
- [ ] Multi-server shared memory with fault tolerance
- [ ] Transparent paging on Linux (`userfaultfd`, zswap); RDMA, NVMe-oF, CXL back ends (needs hardware)
- [ ] KV-cache tiering for LLM inference with a cost-per-token policy

## Runtime Engine
- [x] Windows route: console binary run under Wine with the reference checksum (v0.4)
- [ ] Graphical Windows applications; Windows VM route
- [x] Read-only input files in the micro-VM (v0.2)
- [ ] OCI containers, controlled network, writable shared folders
- [x] Remote execution of Linux binaries in a sandboxed runner (v0.3, loopback only)
- [ ] Remote desktop / application streaming
- [ ] Head-to-head comparison with Docker Desktop, UTM, Parallels, CrossOver

## SPATIAL Q
- [x] QIR export, base profile, validated with pyqir (v0.2)
- [x] OpenQASM 2 export for Cirq / PennyLane importers (v0.3; checked with Qiskit's parser only)
- [x] QIR adaptive profile for dynamic circuits, verified with pyqir (v0.5)
- [ ] Verified round-trips with Cirq, PennyLane, Q#, CUDA-Q
- [x] Real QPU backend: IBM Quantum through qiskit-ibm-runtime (v0.6)
- [x] A first circuit executed on real quantum hardware: Bell pair on ibm_marrakesh, 90 % correlated (`benchmarks/results/qpu_bell.json`)
- [x] Noisy simulator compared with real hardware on 5 circuits; asymmetric readout error added (v0.7, `docs/QPU.md`)
- [ ] Repeat on other devices and days; noise that depends on the qubit pair
- [x] Sub-kernels with qubit parameters (v0.2)
- [x] Compiled classical part (to Python bytecode, v0.5)
- [ ] Native compilation of the classical part
- [x] Depolarising noise in the built-in simulator (v0.2)
- [x] Cost estimation per shot from caller-supplied prices (v0.3)
- [ ] Richer noise models

## Other engines
- [x] AI: toy transformer with a real KV cache, restore-versus-recompute measured through the tiered store (v0.4)
- [ ] AI: real LLM inference, KV-cache routing, vLLM / llm-d integration (needs hardware)
- [x] Scientific: second validated job (RK4 ODE); Simulation: N-body; Intelligence: predictor wired to the scheduler; Holographic: hologram synthesis + numerical reconstruction (v0.4)
- [ ] Scientific: domain solvers and HPC connectors
- [ ] Simulation / Intelligence: multiphysics, digital twins, learned models
- [ ] Holographic: real-time rendering, display hardware

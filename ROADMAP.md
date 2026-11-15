# Roadmap

What exists is a prototype. This is what is missing, by area. Items marked **needs hardware** cannot be validated on a laptop.

## Cross-cutting
- [ ] Test offload and remote memory between **two real machines** (needs hardware)
- [x] `nvidia-smi` detection in `spatial audit` (v0.3; parser tested, never run on a real NVIDIA GPU)
- [ ] Validation of the scheduler on Linux + NVIDIA (needs hardware)
- [ ] Real per-run energy measurement (`powermetrics` as root, or an external meter)
- [x] Channel encryption (SWP/1: AES-256-GCM, v0.2) and far-page encryption
- [x] Tamper-evident (hash-chained) ledger
- [ ] Forward secrecy / TLS, per-tenant permissions, signed audit log
- [ ] Publish to PyPI; English translation of the reports in `docs/`

## Compute Engine
- [x] Priority task queue across N workers with re-queue on worker failure (v0.2, loopback only)
- [ ] GPU orchestration (CUDA / Metal), local and remote (needs hardware)
- [x] Cost objective in the scheduler (v0.3)
- [ ] Cloud provider integration
- [ ] More workload families than the Mandelbrot reference

## Tiered memory
- [ ] Rewrite hot paths in Rust or C++; keep Python as the decision layer
- [x] Encryption and replication of far pages (v0.2)
- [ ] Multiple writers
- [ ] Transparent paging on Linux (`userfaultfd`, zswap); RDMA, NVMe-oF, CXL back ends (needs hardware)
- [ ] KV-cache tiering for LLM inference with a cost-per-token policy

## Runtime Engine
- [ ] Windows route: Wine or a licensed Windows image, shown working end to end
- [x] Read-only input files in the micro-VM (v0.2)
- [ ] OCI containers, controlled network, writable shared folders
- [x] Remote execution of Linux binaries in a sandboxed runner (v0.3, loopback only)
- [ ] Remote desktop / application streaming
- [ ] Head-to-head comparison with Docker Desktop, UTM, Parallels, CrossOver

## SPATIAL Q
- [x] QIR export, base profile, validated with pyqir (v0.2)
- [x] OpenQASM 2 export for Cirq / PennyLane importers (v0.3; checked with Qiskit's parser only)
- [ ] QIR adaptive profile; verified round-trips with Cirq, PennyLane, Q#, CUDA-Q
- [ ] Real QPU backend (needs a provider account)
- [x] Sub-kernels with qubit parameters (v0.2)
- [ ] A compiled (not interpreted) classical part
- [x] Depolarising noise in the built-in simulator (v0.2)
- [x] Cost estimation per shot from caller-supplied prices (v0.3)
- [ ] Richer noise models

## Other engines
- [ ] AI: real distributed inference, KV-cache routing, vLLM / llm-d integration (needs hardware)
- [ ] Scientific: domain solvers and HPC connectors
- [ ] Simulation / Intelligence: multiphysics, digital twins, learned models
- [ ] Holographic: everything beyond the data model

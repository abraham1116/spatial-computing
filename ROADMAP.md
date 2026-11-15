# Roadmap

What exists is a prototype. This is what is missing, by area. Items marked **needs hardware** cannot be validated on a laptop.

## Cross-cutting
- [ ] Test offload and remote memory between **two real machines** (needs hardware)
- [ ] Linux + NVIDIA port of `spatial audit` and the compute scheduler (needs hardware)
- [ ] Real per-run energy measurement (`powermetrics` as root, or an external meter)
- [ ] Channel and page encryption (TLS / WireGuard), per-tenant permissions, signed audit log
- [ ] Publish to PyPI; English translation of the reports in `docs/`

## Compute Engine
- [ ] Multi-task queue and priorities; scheduling across N workers
- [ ] GPU orchestration (CUDA / Metal), local and remote (needs hardware)
- [ ] Cloud provider integration; cost-aware choice at run time
- [ ] More workload families than the Mandelbrot reference

## Tiered memory
- [ ] Rewrite hot paths in Rust or C++; keep Python as the decision layer
- [ ] Encryption and replication of far pages; multiple writers
- [ ] Transparent paging on Linux (`userfaultfd`, zswap); RDMA, NVMe-oF, CXL back ends (needs hardware)
- [ ] KV-cache tiering for LLM inference with a cost-per-token policy

## Runtime Engine
- [ ] Windows route: Wine or a licensed Windows image, shown working end to end
- [ ] OCI containers, controlled network and shared folders in the micro-VM
- [ ] Remote execution and remote desktop / application streaming
- [ ] Head-to-head comparison with Docker Desktop, UTM, Parallels, CrossOver

## SPATIAL Q
- [ ] QIR export; interop with Cirq, PennyLane, Q#, CUDA-Q
- [ ] Real QPU backend (needs a provider account)
- [ ] Sub-kernels, user-defined gates, a compiled (not interpreted) classical part
- [ ] Resource and cost estimation per shot; noise models

## Other engines
- [ ] AI: real distributed inference, KV-cache routing, vLLM / llm-d integration (needs hardware)
- [ ] Scientific: domain solvers and HPC connectors
- [ ] Simulation / Intelligence: multiphysics, digital twins, learned models
- [ ] Holographic: everything beyond the data model

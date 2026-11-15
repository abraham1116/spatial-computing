# Changelog

## 0.12.1
- Protocol: handshake timeout (a silent peer used to hold a thread forever), 512-connection cap, listen backlog 1,024 (the default of 5 refused simultaneous reconnects), malformed authenticated records no longer kill the handler thread.
- Hub: `--state-file` persistence with atomic snapshots; running tasks requeued after a restart; late results accepted.
- New tests and benchmarks: `tests/test_hardening.py`, `benchmarks/bench_scale.py` (100, 300, 1,000 simulated agents), interconnect at N=6 and N=16.

## 0.12.0
- New: virtual interconnect (`spatial.interconnect`): ring, halving-doubling and tree all-reduce plus broadcast between processes over SWP/2, with an alpha-beta cost model. Measured: the shared-link model picked the fastest algorithm in 1 of 6 sizes; calibrated per algorithm, 4 of 6 on an unseen rank count. About 3,000x below NVLink 5 on bandwidth (vendor figure).
- New: portable kernels (`spatial.kernel`): one kernel source, Numba CPU, generated Metal and generated CUDA C (CUDA never run). Integer kernel bit-identical on CPU and Metal; planner families `pk_mandel` and `pk_collatz` (4 of 6 device choices right).
- Fleet hub: weighted fair share between tenants, all-or-nothing gang scheduling with node holds, cache-affinity routing. Still pull-based: nothing running is preempted.
- Docs: `docs/INTERCONNECT.md`, `docs/KERNELS.md` (includes why ZLUDA is not used).

## 0.11.0
- New: virtual accelerator fabric. The same job (`mandel_f32`) has CPU, Metal GPU and NVIDIA (`numba.cuda`, never run on real hardware) implementations; the planner picks by measured cost. 7 of 7 device choices correct on the reference Mac (CPU up to n = 600, Metal GPU from n = 1024). `spatial devices` lists the devices.
- Per-device prices (`Prices.device_usd_h`).
- Docs: `docs/FABRIC.md`.

## 0.10.0
- New: one objective for every engine. `spatial.unified.Planner` and `spatial optimize`: each engine proposes priced options for a job (compute/simulation/scientific/holographic families, fleet nodes, tiered memory, runtime routes, quantum backends, AI cache); one function ranks them by cost within the stated constraints; executing a plan records the estimate beside reality and calibrates the next one.
- Science, simulation and holographic workloads (heat, N-body, hologram, option pricing, ODE) join the allow-list, so the planner and the fleet can run them.
- Decision quality measured by running every option: 12 of 13 tuning cases and 12 of 12 held-out cases picked the truly fastest option (`benchmarks/bench_unified.py`).
- Docs: `docs/OBJECTIVE.md`.

## 0.9.0
- New: Spatial Fleet. `spatial agent` measures a machine continuously and runs allow-listed tasks; `spatial serve hub` stores the fleet's measurements, places tasks, and produces recommendations with evidence; `spatial fleet status|advise|submit|result`.
- Fix: the hash-chained ledger could break under concurrent writers (one thread per connection). Now locked; test added.
- Docs: `docs/INFRASTRUCTURE.md`.

## 0.8.0
- Core: SWP/2 with forward secrecy (ephemeral X25519 mixed with the secret); scoped credentials with expiry, quotas, revocation and a hash-chained audit log (`spatial token init|issue`, `--master-key-file` on every service).
- SPATIAL Q: commutation-aware optimizer rules, fuzz-tested.
- Benchmarks: CPU runs repeated 9 and 7 times with quartiles; new 24 GiB dataset-larger-than-RAM test.
- Docs: `docs/TESTS_NOT_DONE.md` and ready-to-run hardware scripts in `benchmarks/hardware/`.
- CI: Python 3.10, 3.11 and 3.13 added.

## 0.7.0
- SPATIAL Q: asymmetric readout error in the simulator (`readout=(p01, p10)`), motivated by real hardware data.
- Benchmark `bench_qpu.py`: one batched IBM job, ideal / depolarising / readout models fitted and compared (`docs/QPU.md`).

## 0.6.1
- Fix: the `qpu` backend now raises a clear BackendUnavailable when `qiskit-ibm-runtime` is not installed.

## 0.6.0
- SPATIAL Q: real QPU backend for IBM Quantum (`qpu` extra); refuses with the real reason when the token or instance is missing.
- Landing page reorganised around the seven engines and the shared core, with one measured proof per engine.
- Published on PyPI.

## 0.5.0
- Memory: several writers on shared pages (versioned compare-and-swap on the page server).
- SPATIAL Q: QIR adaptive profile for dynamic circuits; classical part compiled to Python bytecode (`--compiled`).
- Docs: `docs/LIMITATIONS.md`, current and in English.

## 0.4.0
- A real, tested component in every engine: AI (toy transformer with KV cache, restore vs recompute through the tiered store), Scientific (RK4 job), Simulation (N-body), Intelligence (predictor drives the scheduler), Holographic (hologram synthesis and numerical reconstruction).
- Runtime: Windows console binary verified under Wine.

## 0.3.0
- Runtime: sandboxed remote runner (`spatial serve runtime`), Linux ELF only, always inside a micro-VM; Wine route picks up a user-level Wine build.
- SPATIAL Q: OpenQASM 2 export (`spatial q qasm2`), shot cost from caller-supplied prices.
- Compute: `nvidia-smi` GPU detection (parser tested, not run on real hardware), `cost` objective in the scheduler.

## 0.2.0
- Core: SWP/1 encrypted protocol (AES-256-GCM), hash-chained ledger.
- Compute: priority task queue across workers with re-queue on failure.
- Memory: encrypted and replicated far tier.
- Runtime: read-only input files in the micro-VM.
- SPATIAL Q: sub-kernels with qubit parameters, depolarising noise, QIR base-profile export.

## 0.1.0
- First public release.

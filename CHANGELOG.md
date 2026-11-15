# Changelog

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

# Changelog

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

# Redundant-execution verification

`spatial.verify` turns the comparison this project already made ad hoc (CPU vs Metal kernel
output, `tests/test_kernel.py`) into a reusable primitive: run the same job twice,
independently, and trust the result only if both runs agree.

```python
from spatial.verify import consensus, verify_kernel
from spatial.kernel.library import collatz

verify_kernel(collatz, ("cpu", "metal"), 64, exact=True, limit=300)   # Consensus(agreed=True, ...)

consensus([result_a, result_b], tolerance=0.01)   # compare two results you already have
```
```bash
spatial verify --family collatz --n 64 --devices cpu,metal --exact --params '{"limit":300}'
```

## Why this, and why now

Three of this project's own markets/plans ride on trusting a result that came from somewhere
cheap and not fully controlled: `spatial.market`'s GPU-arbitrage spread (buy time on the
cheapest live offer), the automotive placement module's "run on a declared, not measured,
chip", and the broader idea of ever running a job on rented, untrusted hardware. Reading a
price (`spatial.market`) is free and risk-free; actually trusting a result computed somewhere
you don't control is a different problem. `docs/MARKET.md` says this plainly: "it does not
prove we can capture that spread" — this module is the first piece of the answer to that,
not the whole answer.

2026's actual production answer to "trust a cheap or untrusted GPU" is not full cryptographic
proof of GPU floating-point execution (research-stage, reported at 373x prover overhead for
generic zkML frameworks on large models) — it is TEEs (~5% overhead) or economic verification
by redundant execution / sampling (1-5% to Nx overhead, N = how many independent runs).
Redundant execution is the one of those three buildable in pure software, with zero new
dependency, and it is exactly what this project's own kernel tests were already doing by hand.

## What this proves, and what it does not

**Proves**: if two independent executions of the same deterministic job disagree, at least one
of them is wrong — a real, checkable signal, demonstrated here against this project's own CPU
and Metal back ends (bit-exact for integer kernels, within a stated tolerance for float
kernels, same numbers already measured in `docs/KERNELS.md`).

**Does not prove**:
- **Not cryptographic.** No zkML, no TEE attestation. A result that agrees was not proven
  correct by any mathematical guarantee — it was only shown to match an independent run.
- **Not collusion-proof.** Two providers that both return the same wrong answer (by bug or by
  design) pass this check. Redundant execution catches an honest mistake or a lazy/faulty
  provider, not a coordinated one.
- **No real untrusted provider tested here.** The only two independent "providers" actually
  exercised in this repository are this project's own CPU and Metal back ends on one Mac —
  honest, measured, but not a test against a real rented, untrusted machine. Renting two
  independent listings (e.g. two different Vast.ai offers) and running a job on each is a
  separate, later, money-spending step that needs explicit go-ahead each time, same boundary
  `spatial.market` already draws between reading a price and renting hardware.
- **No availability or SLA guarantee.** A disagreement is detected after both runs finish; this
  does not make a flaky or slow provider fast or reliable.

## Limits

- Exact mode requires identical shapes and, for integers, bit-for-bit equality; it is not
  meant for non-deterministic workloads (e.g. anything using an unseeded random number or
  depending on wall-clock timing in its output).
- Only pairwise/all-vs-first comparison, no majority vote among 3+ results, no weighting by a
  provider's past reliability (that is `spatial.market`'s `reliability` field, a separate,
  unrelated number from Vast.ai's own host score).
- No cost model: running a job twice (or N times) costs roughly N times as much; this module
  does not decide whether that trade-off is worth it for a given job, it only answers "did they
  agree."

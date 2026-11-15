# Contributing

Thanks for helping. This is a research prototype with one rule: **no claim without a measurement**.

## Ground rules

1. **Do not simulate results.** A feature that cannot work on a machine must say so (see how `qpu` and the Windows route refuse). No faked benchmarks, no placeholder numbers.
2. **Measure before claiming.** A performance or cost claim needs a reproducible benchmark in `benchmarks/` and a result that equals the reference.
3. **Never present non-RAM as RAM.** Compressed, on-disk and remote memory are `far_memory`.
4. **Safe by default.** Network servers bind to loopback; exposing a machine needs an explicit flag. No code is executed because a peer sent it.
5. **Small, tested changes.** Every change comes with a test (`pytest`).

## Setup

```bash
git clone https://github.com/abraham1116/spatial-computing && cd spatial-computing
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[quantum,dev]"
pytest
```

## Where help is most useful

See [ROADMAP.md](ROADMAP.md). Good first areas: a Linux/NVIDIA port of `spatial audit`, English translations of the reports in `docs/`, QIR export for SPATIAL Q, more workloads for the compute scheduler, and tests on a second real machine.

## Pull requests

- Open an issue first for anything large.
- Describe the hardware and OS you ran the tests on, and attach benchmark output when performance is involved.
- By contributing you agree that your contribution is licensed under Apache-2.0.

# Spatial Computing

**Measure. Decide. Prove.**

Spatial Computing chooses where and how a workload should run from measurements, and claims a gain only when it is measured. It does not add RAM, cores or GPUs: it compares execution strategies on the hardware you have, trades one resource for another in numbers, and says plainly what it cannot do.

> **Status: v0.7.0, early-stage open-source toolkit.** Everything here was built and measured on a single 2017 MacBook Pro (Intel i7-7660U, 2 cores, 16 GB). Nothing has been proven on a second machine, a data-center GPU or a real quantum computer. See [Limitations](docs/LIMITATIONS.md) and the [site](https://spatial-computing-ecru.vercel.app).

[Français](README.fr.md)

## Install

Python 3.10 or newer.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "spatial-computing[quantum]"
spatial audit
```

From source, to develop:

```bash
git clone https://github.com/abraham1116/spatial-computing && cd spatial-computing
pip install -e ".[quantum,dev]"
pytest
```

Optional Linux micro-VM route (needs QEMU and two files, checked by SHA-256):

```bash
mkdir -p vendor && cd vendor
curl -O https://dl-cdn.alpinelinux.org/alpine/v3.22/releases/x86_64/netboot/vmlinuz-virt
curl -o busybox-x86_64 https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox
shasum -a 256 -c SHA256SUMS
```

## Use

```bash
spatial audit                       # hardware, current usage, limits of this machine
spatial status                      # honest status of every engine
spatial plan app.exe                # detected format + execution routes, with reasons
spatial run  app.elf 600 300        # run through the first feasible route (micro-VM here)
spatial q run examples/03_vqe_hybrid.sq --trace    # SPATIAL Q hybrid program
spatial q qasm examples/04_teleport.sq --args '[1.0]'   # export OpenQASM 3
spatial bench all                   # redo every measurement and regenerate the results table
```

Tiered memory as a library:

```python
from spatial.memory import TieredStore, FileBackend
st = TieredStore(hot_bytes=16 << 20, compressed_bytes=16 << 20,
                 far=FileBackend("/tmp/far.bin"), prefetch=16, keep_far_copy=True)
st.put(0, b"..." * 1000); st.get(0); print(st.stats())
```

## What is in the box

| Engine | Level | Evidence |
|---|---|---|
| Compute Engine (detect, monitor, compare strategies, offload, cost) | operational prototype | `tests/test_compute.py`, `benchmarks/bench_cpu.py` |
| Tiered memory (hot / compressed / far) | operational prototype | `tests/test_memory.py`, `benchmarks/bench_memory.py` |
| Runtime Engine (inspect binaries, route, micro-VM, WASI) | operational prototype | `tests/test_runtime.py`, `benchmarks/bench_runtime.py` |
| SPATIAL Q (language, compiler, IR, OpenQASM 3, simulators) | operational prototype | `tests/test_q.py`, `benchmarks/bench_q.py` |
| AI, Scientific, Simulation, Intelligence, Holographic | first components (toy model, small solvers, numerical optics) | `tests/test_engines.py`, `tests/test_domains.py` |

Measured on the reference machine (AC power): Numba JIT ×31.6 over pure Python with an identical result; 0.88 s to boot an isolated Linux micro-VM on macOS; −75 % local RAM for a skewed-access dataset at 107× the mean access latency; SPATIAL Q simulator fidelity 1.000 against Qiskit up to 16 qubits. Full table and conditions: [docs/RESULTATS.fr.md](docs/RESULTATS.fr.md).

## What it does not do

- It does not add RAM. Compressed, on-disk or remote memory is typed `far_memory`, never `ram`, and a test enforces it.
- It does not confuse virtualization with extra resources.
- It does not claim a QPU speeds anything up: everything in SPATIAL Q is classical simulation, and the `qpu` backend refuses to run until a provider is configured.
- It never exposes your machine: servers bind to `127.0.0.1` and refuse anything else without an explicit `--allow-remote`.

## Open core

The core in this repository is licensed under [Apache-2.0](LICENSE). Advanced placement and cost policies are developed in a separate private package and are not part of this repository.

## Documentation

The site has the full reference: <https://spatial-computing-ecru.vercel.app> (English and French). [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) is current and in English; the other in-repo reports are historical v0.1 notes in French, and English translations are welcome (see [CONTRIBUTING](CONTRIBUTING.md)).

## Contributing

Issues and pull requests are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the [ROADMAP](ROADMAP.md). Report security problems privately, see [SECURITY.md](SECURITY.md).

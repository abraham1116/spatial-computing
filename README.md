# Spatial Computing

**Measure. Decide. Prove.**

One objective for the whole infrastructure: get every job done correctly at the lowest cost, and prove it. Spatial Computing prices every way to run a job across compute, memory, runtime, AI and a fleet of machines, picks the cheapest, and records the estimate next to what really happened. A gain is claimed only when it is measured. It does not add RAM, cores or GPUs: it compares execution strategies on the hardware you have, trades one resource for another in numbers, and says plainly what it cannot do.

> **Status: v0.22.0, early-stage open-source toolkit.** Everything here was built and measured on a single 2017 MacBook Pro (Intel i7-7660U, 2 cores, 16 GB). Nothing has been proven on a second machine or a data-center GPU. See [Limitations](docs/LIMITATIONS.md) and the [site](https://spatial-computing-ecru.vercel.app).

[Français](README.fr.md)

## Install

Python 3.10 or newer.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install spatial-computing
spatial audit
```

From source, to develop:

```bash
git clone https://github.com/abraham1116/spatial-computing && cd spatial-computing
pip install -e ".[dev]"
pytest
```

Optional Linux micro-VM route (needs QEMU and two files, checked by SHA-256):

```bash
mkdir -p vendor && cd vendor
curl -O https://dl-cdn.alpinelinux.org/alpine/v3.22/releases/x86_64/netboot/vmlinuz-virt
curl -o busybox-x86_64 https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox
shasum -a 256 -c SHA256SUMS
```

## Console (accounts, apps, API keys, jobs, billing)
```bash
spatial token init --master-key-file hub.key
spatial serve hub --master-key-file hub.key --port 7700 --usage-file usage.jsonl --revoked-file revoked.txt
spatial platform serve --master-key-file hub.key --hub 127.0.0.1:7700 --usage-file usage.jsonl --revoked-file revoked.txt
# open http://127.0.0.1:8090/ : sign up, create an app, create a node key and a client key
spatial agent --hub 127.0.0.1:7700 --token-file node.tok     # the machine appears in Fleet; submit jobs from Jobs
```
Production (hub, console, HTTPS): `docker compose --env-file deploy/.env up -d --build`. See [docs/PLATFORM.md](docs/PLATFORM.md) and [docs/DEPLOY.md](docs/DEPLOY.md).

## Use

```bash
spatial audit                       # hardware, current usage, limits of this machine
spatial status                      # honest status of every engine
spatial plan app.exe                # detected format + execution routes, with reasons
spatial run  app.elf 600 300        # run through the first feasible route (micro-VM here)
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
| Virtual accelerator fabric (one job, several devices: CPU, Metal GPU, NVIDIA when present) | first components | `tests/test_fabric.py`, `benchmarks/bench_unified.py` |
| Planner (the one objective: price every option across all engines, choose, run, check) | operational prototype | `tests/test_unified.py`, `benchmarks/bench_unified.py` |
| Fleet (agent on every machine + hub: measure, place, recommend, audit) | operational prototype | `tests/test_fleet.py`, `benchmarks/bench_fleet.py` |
| Compute Engine (detect, monitor, compare strategies, offload, cost) | operational prototype | `tests/test_compute.py`, `benchmarks/bench_cpu.py` |
| Tiered memory (hot / compressed / far) | operational prototype | `tests/test_memory.py`, `benchmarks/bench_memory.py` |
| Runtime Engine (inspect binaries, route, micro-VM, WASI, containers incl. ARM64 via emulation) | operational prototype | `tests/test_runtime.py`, `benchmarks/bench_runtime.py` |
| Portable kernels (one source, CPU/Metal/CUDA/HIP/Triton; market-vertical presets) | first components | `tests/test_kernel.py`, `benchmarks/bench_kernel.py` |
| Live GPU market prices (`spatial market`, read-only, no account) | first components | `tests/test_market.py`, [docs/MARKET.md](docs/MARKET.md) |
| In-vehicle multi-chip placement (`spatial automotive`, declared chip specs, no real silicon) | first components | `tests/test_automotive.py`, [docs/AUTOMOTIVE.md](docs/AUTOMOTIVE.md) |
| Redundant-execution verification and fleet screening (`spatial verify`, `spatial screen`; faults injected in tests, not cryptographic, see limits) | first components | `tests/test_verify.py`, `tests/test_screen.py`, [docs/VERIFY.md](docs/VERIFY.md) |
| AI, Intelligence | first components (toy model) | `tests/test_engines.py`, `tests/test_domains.py` |

Measured on the reference machine (AC power): Numba JIT ×31.6 over pure Python with an identical result; 0.88 s to boot an isolated Linux micro-VM on macOS; −75 % local RAM for a skewed-access dataset at 107× the mean access latency. Full table and conditions: [docs/RESULTATS.fr.md](docs/RESULTATS.fr.md).

## What it does not do

- It does not add RAM. Compressed, on-disk or remote memory is typed `far_memory`, never `ram`, and a test enforces it.
- It does not confuse virtualization with extra resources.
- It never exposes your machine: servers bind to `127.0.0.1` and refuse anything else without an explicit `--allow-remote`.

## Open core

The core in this repository is licensed under [Apache-2.0](LICENSE). Advanced placement and cost policies are developed in a separate private package and are not part of this repository.

## Documentation

The site has the full reference: <https://spatial-computing-ecru.vercel.app> (English and French). [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) is current and in English; the other in-repo reports are historical v0.1 notes in French, and English translations are welcome (see [CONTRIBUTING](CONTRIBUTING.md)).

## Contributing

Issues and pull requests are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the [ROADMAP](ROADMAP.md). Report security problems privately, see [SECURITY.md](SECURITY.md).

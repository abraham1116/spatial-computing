# Tests not done

Everything that has **not** been tested, why, what it needs, how to run it, and what result would count as a pass. Nothing in this file is claimed to work. Scripts marked *ready* exist in the repository but have never run on the target hardware.

Status legend: **ready** (script written, needs only the hardware), **design** (procedure described, nothing written), **external** (needs people or services, not code).

Last reviewed: v0.8.0.

## A. Hardware tests

### A1. Second real machine — **ready**
| | |
|---|---|
| Why not done | One machine only. Offload, task queue, shared pages and the remote page server were validated over loopback or an emulated link. |
| Needs | A second computer on the same network, with the project installed. |
| Run | `benchmarks/hardware/two_machines.py` (instructions in its header). `--allow-remote` is explicit consent to accept LAN connections: use it only on a network you control. |
| Pass | Results identical to local; real round-trip time and remote-memory latency recorded; a worker killed mid-run causes the task queue to re-queue and finish (repeat the `test_queue_requeues_when_a_worker_dies` scenario across machines). |
| Cost | None. |

### A2. NVIDIA GPU node — **ready (script) / design (the rest)**
| | |
|---|---|
| Why not done | No GPU server. The integrated Intel GPU is the only GPU measured. |
| Needs | A Linux machine with an NVIDIA GPU and CUDA PyTorch, rented from RunPod, Lambda or similar. Roughly 0.5 to 4 USD for an hour. Set a spend cap first. |
| Run (G1) | `benchmarks/hardware/gpu_node.py`: `spatial audit` GPU detection, matmul TFLOPS (fp32/fp16/bf16), host-to-GPU bandwidth, prefill proxy. |
| Pass (G1) | `nvidia-smi` detection (parser tested, never run for real) reports the right name and VRAM; throughput numbers recorded in `benchmarks/results/gpu_node.json`. |
| Design (G2) | Real LLM: run vLLM with prefix caching on a small open model; replay a prompt trace; record GPU utilization, tokens per second and cost per million tokens with and without KV-cache offload (LMCache or llm-d). Feed measured restore bandwidth and prefill speed into the private KV policy and check its restore-versus-recompute choice against reality. |
| Pass (G2) | The policy picks the cheaper option on at least 90 % of prompts, and the end-to-end cost per token falls by at least 20 % against a tuned baseline (the go/no-go figure of the business plan). If not, say so and revisit the thesis. |
| Design (G3) | Scheduler GPU strategies (CUDA and Metal) next to the CPU ones, same checksum rule. |
| Design (G4) | Cloud provider integration: create, run, destroy an instance from the CLI; compare the cost model's estimate with the actual bill. |

### A3. Energy — **ready**
| | |
|---|---|
| Why not done | `powermetrics` needs administrator rights. The battery gauge froze at 32.5 W between idle and full load, so it cannot measure a run. |
| Needs | You run it with `sudo`, or an external wattmeter. |
| Run | `sudo benchmarks/hardware/energy.sh` (macOS). On AC power, fixed screen brightness, nothing else running. |
| Pass | Idle power and per-strategy marginal joules recorded in `benchmarks/results/energy.json`; the cost model's energy lines then use measured values instead of an assumed 32.5 W. |

### A4. Effect of power source and temperature — **design**
Same benchmark on AC and battery, and cold versus after 10 minutes of load. Earlier observation (unmeasured protocol): about 3 times slower on a low battery. Pass: a table of slowdown versus state of charge.

### A5. Other operating systems and CPUs — **design / partly done by CI**
| Item | State |
|---|---|
| Linux x86_64 (GitHub Actions) | tests run and pass |
| macOS arm64 (GitHub Actions) | tests run and pass |
| Linux arm64, Windows host | not tested |
| Apple Silicon specifics (MLX, Neural Engine, Rosetta for Linux, Virtualization.framework, arm64 guests) | not tested: the reference machine is Intel |
| Python 3.10, 3.11, 3.13 | `requires-python` says 3.10+, CI covers other versions since v0.8; the project was developed on 3.13 |

### A6. Memory hardware — **design, needs hardware**
| Item | Needs | Pass |
|---|---|---|
| Transparent paging on Linux (`userfaultfd`, zswap) | Linux host | An unmodified program larger than RAM runs correctly through the tiered store |
| RDMA backend | RDMA-capable NICs on two hosts | Page fetch latency in the single-digit microsecond range reported by the literature, on our code |
| CXL memory | A server with CXL expansion | Measured latency and bandwidth per tier |
| NVMe-over-Fabrics backend | NVMe-oF target | Same |
| Rewrite of hot paths in Rust or C++ | Rust toolchain (not installed) | At least 10 times lower per-access overhead than the Python version, same results |

## B. Quantum tests

| Id | Test | State | Needs |
|---|---|---|---|
| B1 | More devices and more days; per-qubit-pair noise; error mitigation | design | IBM Quantum plan with time (the open plan has a small monthly quota) |
| B2 | Cost per shot from real prices | partly done: the function exists and refuses to run without caller-supplied prices | The provider's actual tariff |
| B3 | QIR executed on a QIR runtime (Quantinuum, Azure Quantum): exports are only parsed by `pyqir` | design | Provider account |
| B4 | OpenQASM 2 and 3 round trips with Cirq, PennyLane, Q# and CUDA-Q (only Qiskit's parser has been used) | ready to write | `pip install cirq pennylane`; Q# and CUDA-Q need their toolchains |
| B5 | Simulation above about 27 qubits, GPU state vector | design | A GPU with enough memory |
| B6 | Any claim of quantum advantage | **not claimed, not tested** | Out of scope |

## C. Runtime tests

| Id | Test | State |
|---|---|---|
| C1 | Graphical Windows applications under Wine; a Windows VM route with a licensed image | design |
| C2 | OCI containers; comparison against Docker Desktop, UTM, Parallels, CrossOver | design, needs those tools installed (some are paid) |
| C3 | Remote desktop and application streaming | design |
| C4 | A guest with network or writable shared folders (the micro-VM has neither) | design |
| C5 | Adversarial test of the sandbox: malicious ELF trying to escape the micro-VM | design, needs a security professional |

## D. Scale, endurance and security

| Id | Test | State |
|---|---|---|
| D1 | Dataset larger than RAM through the tiered store | **done in v0.8**: 24 GiB logical on a 16 GiB machine with a 512 MiB local budget; 2,648 pages (600 random, 2,048 sequential) verified byte for byte, 0 corrupt; process RSS peaked at 578 MiB; 11.4 GiB on disk; load 305 MB/s; 5 ms mean random access. Disk-backed, not extra RAM. See `benchmarks/results/bigdata.json` |
| D2 | Soak test: hours of continuous use, memory growth, connection leaks | design |
| D3 | Many concurrent clients on the servers (hundreds) | design; the servers are one thread per connection |
| D4 | Independent security review of SWP/2 (forward secrecy was added in v0.8, not reviewed by anyone else) | external |
| D5 | Fuzzing the wire format and the SPATIAL Q parser | design |
| D6 | Verifying every benchmark again after each release | design: add a scheduled job |

## E. Other engines

| Id | Test | State |
|---|---|---|
| E1 | AI: a real language model, model routing, vLLM / llm-d integration | design (see A2-G2) |
| E2 | Scientific: domain solvers against reference codes (OpenFOAM, LAMMPS, ...) | design, needs those codes and HPC time |
| E3 | Simulation: multiphysics, digital twin validated against real sensor data | design, needs data |
| E4 | Intelligence: predictor tested on unseen machines and many workload families | design, needs a second machine and more workloads |
| E5 | Holographic: a physical spatial light modulator; real-time hologram synthesis on a GPU; optical measurement | design, needs hardware |

## F. Business and legal validation (not code)

| Id | Test | State |
|---|---|---|
| F1 | At least 15 conversations with GPU cloud and inference operators | external |
| F2 | A design-partner pilot with a measured saving | external; depends on A2 |
| F3 | Prior-art patent search (no patent database was queried) | external |
| F4 | Trademark availability search ("spatial computing" is a descriptive term used by Apple) | external |
| F5 | Export-control qualification; data-protection review | external |
| F6 | Pricing test | external |
| F7 | Check the financial model's key input (the saving rate) against pilot data | external; depends on F2 |

## What each missing item would change

- **A2 (GPU)** decides whether the commercial thesis holds. Nothing else matters as much.
- **A1 and A3** turn estimates into measurements for distribution and energy.
- **D4 and C5** are required before exposing any service to a network you do not control.
- **B-tests** do not affect the business thesis; they affect the credibility of SPATIAL Q.

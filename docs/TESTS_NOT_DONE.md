# Tests not done

Everything that has **not** been tested, why, what it needs, how to run it, and what result would count as a pass. Nothing in this file is claimed to work. Scripts marked *ready* exist in the repository but have never run on the target hardware.

Status legend: **ready** (script written, needs only the hardware), **design** (procedure described, nothing written), **external** (needs people or services, not code).

Last reviewed: v0.9.0.

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
| Design (G2b) | Run `mandel_f32_cuda` through the planner on the real NVIDIA machine: the code in `spatial/fabric/cuda.py` has never executed. Pass: result within 1e-3 of the CPU variant, the planner picks the GPU for large sizes, estimate error comparable to the Metal case. See [FABRIC.md](FABRIC.md). |
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

## H. Planner tests (the one objective)

| Id | Test | State |
|---|---|---|
| H-1 | Decision quality on a second and third machine (estimates are per machine; does the planner still pick the fastest?) | ready: `python benchmarks/bench_unified.py` and `HELDOUT=1 ...` on each machine |
| H-2 | Real billed money: run on a rented node and compare the planner's dollar estimate with the invoice | design, needs a cloud account |
| H-3 | NVIDIA GPU as a planner option on a real GPU, with its price per hour (the Metal GPU path is tested; the CUDA path is not) | design, needs an NVIDIA machine |
| H-4 | Many more job families and sizes (the 25 cases are numerical kernels and circuit simulation only) | design |
| H-5 | A learned runtime model instead of probes plus a median correction; compare accuracy and probe cost | design |
| H-6 | Real QPU option priced with the provider's tariff and compared with simulators on cost and fidelity | design, needs tariff and QPU time |
| H-7 | Fleet node speed: measure per-node speed instead of assuming it equals this machine's | design, needs several machines |
| H-8 | Real LLM KV-cache policy against a real inference server | **measured in v0.15.0** (`benchmarks/bench_llm.py`, `llm_kvcache.json`): a 946-token prompt, five questions, prefix caching on or off. Recompute 28 to 175 s (median 36 s; noisy: the 2-vCPU VM shared the machine with other work), cached 0.35 to 0.69 s, so reuse saved at least ×41 on the prompt phase (best recompute against worst cached); the 939 shared tokens were reused and the answers were identical in 5 of 5. One small model, CPU, one prompt length. The planner's KV policy is **not** yet calibrated from these numbers; no GPU |

## G. Fleet tests (agent + hub)

| Id | Test | State |
|---|---|---|
| G-1 | Agents on several **real machines** reporting to one hub (today: up to 3 agents on one machine, so every agent reports the same CPU) | ready: `spatial serve hub`, `spatial agent` on each machine, see [INFRASTRUCTURE.md](INFRASTRUCTURE.md) |
| G-2 | Scale: 100 then 1,000 simulated agents against one hub (reports per second, memory, latency of `status`/`advise`) | **done in v0.12.1** on one machine: 1,000 agents reporting every 2 s, 477 reports/s achieved, p50 0.8 ms, p99 15 ms, `status` 36 ms, `advise` 35 ms, hub RSS 109 MiB; 31 connection resets at the 1,000-agent burst (see FLEET numbers in INFRASTRUCTURE.md). Client threads shared the CPU with the hub |
| G-3 | Hub failure and restart (state is in memory: what is lost, how fast agents reconnect), then persistence and high availability | **persistence done in v0.12.1** (`--state-file`: atomic JSON snapshot every 5 s; tasks, queue, tenant usage survive; running tasks are requeued, at-least-once); a hub restarted on the same port is rejoined by its agents and finishes the queued work (test). Measurements are not saved (rebuilt within one report interval). **High availability built in v0.13.0** as active/standby without consensus ([HA.md](HA.md)): about 6.7 s from `kill -9` to a task finishing on the survivor, 3 of 3 trials; no real partition or clock-skew test. With 3 or more hubs a majority election is available (v0.14.0, [HA.md](HA.md)), tested with simulated clocks only |
| G-4 | Recommendation quality: apply each kind of recommendation on a real fleet and re-measure; count how often the predicted saving appears | design, needs a real fleet and operators |
| G-5 | GPU nodes: agent reading real `nvidia-smi` and the GPU-aware placement (`needs: {gpu: true}`) | design, needs an NVIDIA machine |
| G-6 | Dashboard UI and alerting | **done in v0.13.0** ([HA.md](HA.md)): read-only local page, edge-triggered alerts, webhook; tested with a local webhook and a headless browser screenshot; not tested with many nodes or on a phone |
| G-7 | Network faults: packet loss, high latency, partitions between agents and hub | design |
| G-8 | Security: stolen agent token, replayed handshake, hostile agent flooding the hub (quotas exist, never stress-tested) | **partly done in v0.12.1**: replayed handshake rejected, silent peers dropped after 10 s (they held a thread forever before), connection cap of 512, oversized frames refused. Stolen token and flooding by an authenticated agent beyond quotas: not tested; external review still needed |

| G-9 | Fair share, gang and affinity on a real fleet with real tenants (today: unit tests with injected clocks); preemption is not possible with synchronous agents | design |

## I. Interconnect and kernel tests

| Id | Test | State |
|---|---|---|
| I-1 | All-reduce between **real machines** over Ethernet (today: processes on one machine over loopback); fit alpha and beta on a real link | ready: `launch` takes any importable function; needs a multi-host launcher |
| I-2 | RDMA / RoCE / InfiniBand transport and GPU-memory buffers (NCCL-style); comparison with NCCL or MPI on the same hardware | design, needs hardware |
| I-3 | Per-algorithm calibration on more rank counts (N=16, 32, non power of two) and message sizes; today N=4 and 8 only | **partly done in v0.12.1**: N=6 (not a power of two) and N=16 added; N=32 and other message-size grids not run. 16 processes on 2 cores measure CPU contention more than a network |
| I-4 | Generated CUDA C compiled with NVRTC and run on an NVIDIA GPU; compare with the CPU result | needs an NVIDIA GPU (same machine as A2) |
| I-5 | Kernels with shared memory, reductions and tensor-core ops; larger kernel library | **partly done in v0.14.0**: whole-grid sum with threadgroup shared memory on Metal (exact for integers), CPU reduction, CUDA and HIP sources generated and never run. Not built: tiling, tensor cores, other reductions, a larger library |
| I-7 | Generated HIP source compiled with `hipcc` and run on an AMD GPU | needs an AMD GPU and ROCm |
| I-6 | ZLUDA as an optional external runtime on an AMD GPU, with a legal opinion on running CUDA binaries | external, needs AMD hardware and counsel |

## C. Runtime tests

| Id | Test | State |
|---|---|---|
| C1 | Graphical Windows applications under Wine; a Windows VM route with a licensed image | **partly done in v0.15.0**: Wine's own Notepad was started and a Wine-owned on-screen window of 847 x 635 appeared (found through CoreGraphics, `benchmarks/hardware/wine_windows.swift`); window contents were not captured (no screen-recording permission), and no application other than Notepad was tried. Windows VM route: not built (no licence) |
| C2 | OCI containers; comparison against Docker Desktop, UTM, Parallels, CrossOver | **partly done in v0.15.0**: the `container` route runs a static Linux ELF in Docker (via Colima) or Podman: read-only root, no network, no capabilities, non-root, 256 MiB, 64 processes (tests check each of these). Podman 5.8.10 (applehv machine) passes the same three container tests (`SPATIAL_OCI=podman`). Not done: comparison with Docker Desktop, UTM, Parallels, CrossOver (not installed or paid) |
| C3 | Remote desktop and application streaming | **built in v0.16.0**: `spatial desktop xterm|xclock|mousepad` runs the app in a container (Xvfb, openbox, x11vnc) and serves it through noVNC, published on 127.0.0.1 with a one-time password, no capabilities, read-only root, 512 MiB. Verified: the xterm window rendered in a browser through noVNC (screenshot), a real RFB banner behind the websocket, loopback-only listener, unknown apps refused (a test). Added later in v0.17.0: clipboard off switch and a view-only password, verified with a real RFB client (the watcher's keystrokes did nothing, the owner's command ran). Several people can connect at once (shared session). Added in v0.18.0: single-file upload and download through the container runtime (binary-safe, 16 MiB, safe names, tested), `xcalc`. Not done: audio, a file-manager window, drag and drop, a real network |
| C4 | A guest with network or writable shared folders (the micro-VM has neither) | **done for the container route in v0.15.0**: `allow_network` and `share_dir` (a copy into a volume and back, no links followed); the micro-VM still has neither |
| C5 | Adversarial test of the sandbox: malicious ELF trying to escape the micro-VM | design, needs a security professional |

## D. Scale, endurance and security

| Id | Test | State |
|---|---|---|
| D1 | Dataset larger than RAM through the tiered store | **done in v0.8**: 24 GiB logical on a 16 GiB machine with a 512 MiB local budget; 2,648 pages (600 random, 2,048 sequential) verified byte for byte, 0 corrupt; process RSS peaked at 578 MiB; 11.4 GiB on disk; load 305 MB/s; 5 ms mean random access. Disk-backed, not extra RAM. See `benchmarks/results/bigdata.json` |
| D2 | Soak test: hours of continuous use, memory growth, connection leaks | **partly done in v0.14.0** (`benchmarks/soak.py`): hub, 3 agents, a client submitting a task every 0.5 s with connection churn, and a dashboard polling, 15 then 12 minutes on one Mac. No errors (1,758 then 1,419 tasks), file descriptors and threads flat, agents flat at 64 MiB. First run: hub RSS grew +12.5 MiB/h because finished tasks were kept forever; fixed with a cap (`--max-finished`, default 5,000, and a cap on cache-affinity keys). Second run with a cap of 300: RSS 64 to 65 MiB, slope +5 MiB/h which 12 minutes cannot tell from noise. **Minutes, not hours or days** |
| D3 | Many concurrent clients on the servers (hundreds) | **partly done in v0.12.1**: 100, 300 and 1,000 simulated agents against one hub ([scale.json](../benchmarks/results/scale.json)); found and fixed a listen backlog of 5 that refused simultaneous reconnects. Agents were threads of one process on the same 2-core Mac; one thread per connection remains |
| D4 | Independent security review of SWP/2 (forward secrecy was added in v0.8, not reviewed by anyone else) | external |
| D5 | Fuzzing the wire format and the SPATIAL Q parser | **partly done in v0.12.1**: random bytes and tampered records against the server, malformed authenticated plaintext, random requests to the hub handler, 1,500 mutated SPATIAL Q programs; no crash. Seeded random tests, not coverage-guided fuzzing |
| D6 | Verifying every benchmark again after each release | **done in v0.14.0**: `benchmarks/verify.py` re-checks the properties behind the saved results (exact collectives, decision regret, kernel parity, 100-agent load, security tests) and `.github/workflows/verify.yml` runs it every Monday on Linux and macOS. Shared runners are noisy: a failure means look, not that the claim is false |

## E. Other engines

| Id | Test | State |
|---|---|---|
| E1 | AI: a real language model, model routing, vLLM / llm-d integration | **partly done in v0.15.0**: a real model (Qwen2.5-0.5B Q4, llama.cpp server in a container, CPU, 2 vCPUs) behind `spatial.ai.llm`; see H-8. Not done: model routing, vLLM / llm-d, a GPU, a larger model |
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

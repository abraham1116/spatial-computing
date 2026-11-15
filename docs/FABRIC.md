# Virtual accelerator fabric

One job, described once, placed on whichever device is cheapest: the CPU, a Metal GPU, an NVIDIA GPU, a remote node. This is the part of "what NVIDIA does" that can be done in software without emulating anything and without touching NVIDIA's intellectual property.

## What it is not
- **Not CUDA emulation.** NVIDIA's CUDA licence forbids using translation layers to run CUDA code on other hardware (clause added from CUDA 11.6; see the research note). We do not translate or reimplement CUDA.
- **Not a virtual NVLink.** Interconnect bandwidth is physics, not software.
- **Not a replacement for NVIDIA's own orchestration** (KAI/Run:ai, Dynamo): NVIDIA open-sourced those; we integrate, we do not compete.

## What it is
Each device runs its **own native implementation** of the same job. The planner (see [OBJECTIVE.md](OBJECTIVE.md)) probes each implementation on reduced sizes, checks they agree, and picks the cheapest for the real size and the stated constraints.

| Device | Backend | State |
|---|---|---|
| CPU | Numba, all cores | tested |
| Metal GPU (macOS) | Swift program compiled on first use | tested on an Intel Iris Plus 640 |
| NVIDIA GPU | `numba.cuda` kernel | **written, never run on real NVIDIA hardware**; rejected with a reason when no CUDA device is visible |
| Remote node | Fleet hub | tested on loopback |

```bash
spatial devices
spatial optimize compute --family mandel_f32 --params '{"n":2048,"iters":200}' --execute
```

## Measured (benchmarks/bench_unified.py with FABRIC=1, one 2017 MacBook Pro)
Same Mandelbrot job in float32 on the CPU and on the integrated GPU; every option was run for real.

| Size n | Planner chose | Truly fastest | Estimate error |
|---|---|---|---|
| 32, 128, 300, 600 | CPU | CPU | -23 %, -30 %, -9 %, +1 % |
| 1024, 2048, 3000 | Metal GPU | Metal GPU | +8 %, +54 %, -13 % |

7 of 7 correct. The crossover (between 600 and 1024) comes from the probes themselves: a GPU launch has a fixed cost that small jobs cannot amortise. CPU and GPU totals agree to about 3 in a million (float32 rounding).

## Related
- [KERNELS.md](KERNELS.md): write a kernel once; CPU, Metal and generated CUDA C. [INTERCONNECT.md](INTERCONNECT.md): collectives between workers.

## Limits
- Two hand-written job families (`mandel_f32`) plus the portable-kernel families (`pk_mandel`, `pk_collatz`). The planner and the fleet already take any family registered in `workloads.py`.
- The NVIDIA path is unproven until test A2 runs on a real GPU.
- Estimates are per machine and per probe; a different GPU needs its own probes (the planner does this at each plan).
- No memory-transfer model yet (host-to-device copies) beyond what the probes happen to include.

# Virtual interconnect (collectives over SWP/2)

The part of "what NVLink does" that exists in software: N workers combine their data (all-reduce, broadcast) over an encrypted channel, and the system chooses the algorithm from a measured cost model. It does **not** make a link faster. NVLink is silicon and copper; this is a software layer over whatever link exists (loopback, Ethernet, later RDMA).

## What is built
`spatial/interconnect/`

| File | Role |
|---|---|
| `comm.py` | `Comm(rank, size)`: point-to-point send/recv and barrier over SWP/2; `launch(size, fn, ...)` starts N OS processes |
| `collectives.py` | ring, recursive halving-doubling and binomial-tree all-reduce, plus broadcast; `allreduce(..., algo="auto")` |
| `model.py` | alpha-beta cost model `t = alpha + M/beta`, predicted time per algorithm, weighted link fit, per-algorithm calibration |
| `tasks.py` | link measurement, correctness check, timing |

Predicted all-reduce time for M bytes over N ranks (Thakur et al. 2005):

| Algorithm | Time | Good for |
|---|---|---|
| ring | `2(N-1)·alpha + 2(N-1)/N · M/beta` | large messages |
| halving-doubling | `2·log2(N)·alpha + 2(N-1)/N · M/beta` (N a power of two) | medium messages |
| tree | `2·log2(N)·(alpha + M/beta)` | small messages |

## Measured (benchmarks/bench_interconnect.py, one 2017 MacBook Pro, 2 cores, AC power)
N ranks are N processes on this machine over encrypted loopback: the numbers describe the software layer, not a network. Eight processes on two cores also compete for the CPU.

- Results are correct: every algorithm matches the sum computed directly (tests, `tests/test_interconnect.py`).
- Fitted link: alpha 152-190 µs per message, beta about 720-730 MB/s.
- Peak bus bandwidth observed: 210-285 MB/s across two runs. NVLink 5 is quoted by NVIDIA at 900 GB/s per direction (vendor figure), about **3,000 to 4,000 times faster**. That gap is the reason this layer is not an NVLink replacement.
- **The uncalibrated model chose the fastest algorithm in only 1 of 6 sizes** for N=4 and 1 of 6 for N=8 (mean regret 1.13x and 1.52x). It always picked halving-doubling; in practice tree was faster for small messages and ring for large ones, because the real cost per message depends on how many sends and receives a rank does per step, which the shared alpha-beta fit does not see.
- **Calibrating each algorithm separately** fixes most of it: fitted on N=4 and judged on N=8 (a rank count it never saw), 4 of 6 right, mean regret 1.11x; leave-one-size-out on N=8, 4 of 6 right, regret 1.04x. The misses sit near ties.

| N=8, size | ring | halving-doubling | tree |
|---|---|---|---|
| 1 KiB | 10.4 ms | 4.2 ms | **2.0 ms** |
| 1 MiB | 22.9 ms | **13.8 ms** | 15.5 ms |
| 16 MiB | **228 ms** | 289 ms | 369 ms |

### More rank counts (second run, v0.12.1)
| N | uncalibrated model right | calibrated on N=4 only, judged here |
|---|---|---|
| 6 (not a power of two: ring and tree only) | 4 of 6 | 5 of 6, mean regret 1.07x |
| 16 | 1 of 6 | 3 of 6, mean regret 1.27x |
Run to run the same benchmark moved: N=4 to N=8 calibrated was 4 of 6 in one run and 3 of 6 in the next; leave-one-size-out on N=8 was 4 of 6 then 6 of 6. Treat "calibrated beats uncalibrated, with regret 1.0x to 1.3x" as the finding, not any single count. Sixteen processes on two cores measure CPU contention more than a link.

## Limits
- One machine, loopback, N = 4, 6, 8 and 16, a single benchmark session per figure. No real network, no RDMA, no GPU memory (all data are NumPy arrays in host RAM).
- Python and encryption dominate: this is not competitive with NCCL or MPI on speed, and does not try to be.
- Halving-doubling needs N a power of two; other N use ring or tree.
- No fault tolerance: a dead rank stops the collective with a timeout.
- Prior art exists and is mature (NCCL, MPI, UCC, MSCCL++, Gloo). Value here is a cost-model-driven, encrypted, hardware-neutral layer that feeds the same planner, not a new algorithm.

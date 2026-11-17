# Portable kernels

One kernel, written once in a small typed subset of Python, runs on the CPU (Numba), on a Metal GPU (generated Metal Shading Language), and is emitted as CUDA C, HIP, and **Triton** source. It does not translate or run CUDA code and uses nothing from NVIDIA: the source language is ours and each back end is generated from its syntax tree. Same idea as Triton or SYCL, at a much smaller scale — and Triton itself is one of the back ends we generate for, not something we run: see "Triton" below.

The library is not only scientific kernels: `batch_score` is the same per-element placement problem applied to a batch-scoring shape (fraud/risk, ranking, recommendation, anomaly detection — any software that scores many independent items). Software and hardware are the same placement problem to the planner; it does not care what the numbers mean.

**Verticals** (`pk_rtb`, `pk_credit`, `pk_claims`, `pk_alerts`, `pk_moderation`, `pk_telecom`): six presentation names over this ONE `batch_score` kernel — real-time ad-bid scoring, credit/loan applications, insurance claims, SIEM security alerts, content moderation, and telecom billing/fraud all score many independent items in a batch, the same shape. No per-vertical model, no real data, no new code path: a test checks each one returns bit-for-bit the same result as `pk_batch_score` for the same inputs, so the name can never silently drift from the math.

## Why not ZLUDA
ZLUDA (Rust, dual Apache-2.0 / MIT) runs unmodified CUDA programs on non-NVIDIA GPUs, in practice AMD ones. We did not use it:
- It needs an AMD GPU with ROCm (Linux or Windows). Reports mention work towards Intel GPUs; nothing we could test on macOS. The reference machine is an Intel Mac with Intel graphics and Metal: it cannot run it at all.
- It solves another problem: executing existing CUDA binaries elsewhere. NVIDIA's CUDA licence forbids translation layers for that purpose (clause added in CUDA 11.6), and AMD's funding ended in 2024. Press reports in 2026 (Phoronix, Byteiota; secondary sources) say it is still active and volunteer-driven, with CUDA 13.1 compatibility and a v6 release, and that its maintainers target AMD and, in progress, other vendors. The code licence is permissive; the exposure comes from running NVIDIA's libraries and binaries through it. We have not had a legal opinion.
- Our planner needs several native implementations whose cost it can measure. A translation layer gives one implementation on one extra device, hides the cost model, and adds a legal question.
Optional, later: ZLUDA could be listed as an external runtime for a customer who already runs CUDA on AMD hardware. Not bundled, not tested.

## Language
```python
from spatial.kernel import kernel

@kernel
def collatz(i: int, j: int, n: int, limit: int):
    x = i * n + j + 1
    k = 0
    while x != 1 and k < limit:
        if x % 2 == 0:
            x = x // 2
        else:
            x = 3 * x + 1
        k += 1
    return k
```
`i, j, n` are row, column and grid size; extra parameters are `int` or `float`. Statements: assignment, `+= -= *=`, `while`, `if/else`, `for k in range(a)`, one final `return`. Expressions: arithmetic, comparisons, `and/or/not`, `int() float() sqrt sin cos exp log floor abs min max`. The returned value is stored as `uint32` in `out[i, j]`. Anything else raises `KernelError` with a line number. Floats are float32 everywhere; ints are 32-bit everywhere (the CPU wraps at each assignment so it matches the GPU's overflow).

```python
kernel.run("cpu", 512, limit=1000)       # Numba
kernel.run("metal", 512, limit=1000)     # compiled at run time
print(kernel.to_metal()); print(kernel.to_cuda_c()); print(kernel.to_hip()); print(kernel.to_triton())
```
Library: `mandelbrot`, `collatz` (integer), `waves` (sin/cos), `batch_score` (fraud/risk/ranking/anomaly-shaped batch scoring, synthetic signals and weights, no trained model). Planner families: `pk_mandel`, `pk_collatz`, `pk_batch_score`.

## Triton
`to_triton()` emits a `@triton.jit` kernel: one Triton "program" per output pixel (`tl.program_id(axis=0/1)` for column/row), the same one-thread-per-pixel shape as the CUDA back end. **Generated only, like CUDA and HIP: this source has never been passed to `triton.jit`, never compiled, never run** — there is no NVIDIA, AMD, or Intel GPU here for Triton to target, and no `triton` package installed. `KernelError` names the device when `run()`/`reduce()` is asked for `"triton"`. Known gaps, left honest rather than silently wrong: integer `//` is generated as a cast through float32 (truncates toward zero, matching this language's C semantics) because Triton's own `//` floors like Python's; `and`/`or` become `&`/`|` after boolifying each side, since tensors have no short-circuit evaluation; there is no reduction variant (`to_triton` has no `reduce=` argument), since Triton's own cross-program reduction does not map onto the single-pass threadgroup shape the other back ends use.

## Measured (benchmarks/bench_kernel.py, 2017 MacBook Pro, Intel Iris Plus 640)
- Integer kernel: CPU and Metal outputs are **bit-identical**, including 32-bit overflow.
- Float kernels agree to within float32 rounding: under 1 % of Mandelbrot pixels differ near the set boundary; the `waves` values differ by at most 3 units out of about 16,000.
- Planner device choice from reduced probes: **4 of 6 right**, mean regret 1.09x. Both misses sit at the CPU/GPU crossover (Mandelbrot n=512: 36 vs 33 ms; collatz n=512: 54 vs 38 ms).
- The first version picked the CPU for large collatz jobs because the planner rejected the GPU: "result differs from the other variants". The cause was a real semantic difference (CPU 64-bit integers against GPU 32-bit); making the CPU wrap at 32 bits fixed it, and a test now covers it.

## Reductions and shared memory (v0.14.0)
`kernel.reduce("cpu" | "metal", n, **params)` returns the sum of the kernel's output over the whole grid (uint64 accumulation).
- CPU: a Numba parallel reduction.
- Metal: 16 x 16 threads per threadgroup add their values pairwise in a 256-entry `threadgroup` array with barriers; one partial sum per group, added on the host. Tested exact against the CPU for integer kernels at n = 16, 37, 100 and 256 (sizes that are not multiples of 16 included) and within 1 % for a float kernel.
- `to_cuda_c(reduce=True)` and `to_hip(reduce=True)` generate the same algorithm with `__shared__` and `__syncthreads()`. **HIP (AMD) and CUDA sources are generated only: never compiled, never run** (no AMD or NVIDIA GPU here).
- Names that would clash with the generated code (`out`, `partial`, `total`, `_sp_*`...) are refused.

## Limits
- **CUDA C, HIP, and Triton are generated and never compiled or run** (no NVIDIA, AMD, or Intel GPU, no NVRTC, no `triton` package here). The `cuda`, `hip`, and `triton` devices refuse to run and say so.
- Two kernel shapes: a 2-D per-element map and a whole-grid sum. Shared memory is used only inside the built-in reduction; you cannot write your own tiled kernel, use tensor cores, or other reductions (min, max, histogram).
- Work scales as n² in the planner's model; data-dependent kernels (collatz) are only roughly proportional, which is why misses happen near the crossover.
- Integer `%` and `//` follow C (truncation), not Python (floor), for negative values.
- No host-device transfer model beyond what the probes include.

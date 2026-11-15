# Portable kernels

One kernel, written once in a small typed subset of Python, runs on the CPU (Numba), on a Metal GPU (generated Metal Shading Language), and is emitted as CUDA C for NVIDIA. It does not translate or run CUDA code and uses nothing from NVIDIA: the source language is ours and each back end is generated from its syntax tree. Same idea as Triton or SYCL, at a much smaller scale.

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
print(kernel.to_metal()); print(kernel.to_cuda_c())
```
Library: `mandelbrot`, `collatz` (integer), `waves` (sin/cos). Planner families: `pk_mandel`, `pk_collatz`.

## Measured (benchmarks/bench_kernel.py, 2017 MacBook Pro, Intel Iris Plus 640)
- Integer kernel: CPU and Metal outputs are **bit-identical**, including 32-bit overflow.
- Float kernels agree to within float32 rounding: under 1 % of Mandelbrot pixels differ near the set boundary; the `waves` values differ by at most 3 units out of about 16,000.
- Planner device choice from reduced probes: **4 of 6 right**, mean regret 1.09x. Both misses sit at the CPU/GPU crossover (Mandelbrot n=512: 36 vs 33 ms; collatz n=512: 54 vs 38 ms).
- The first version picked the CPU for large collatz jobs because the planner rejected the GPU: "result differs from the other variants". The cause was a real semantic difference (CPU 64-bit integers against GPU 32-bit); making the CPU wrap at 32 bits fixed it, and a test now covers it.

## Limits
- **CUDA C is generated and never compiled or run** (no NVIDIA hardware, no NVRTC here). The `cuda` device refuses to run and says so.
- One kernel shape: a 2-D grid, per-element, no shared memory, no reductions, no inter-thread communication, output a `uint32` array. Real GPU programming (tiling, shared memory, tensor cores) is not expressible.
- Work scales as n² in the planner's model; data-dependent kernels (collatz) are only roughly proportional, which is why misses happen near the crossover.
- Integer `%` and `//` follow C (truncation), not Python (floor), for negative values.
- No host-device transfer model beyond what the probes include.

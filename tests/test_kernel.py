"""Portable kernels: same source, same result on CPU and Metal; unsupported code is refused."""
import numpy as np
import pytest

from spatial.fabric import metal
from spatial.kernel import KernelError, kernel
from spatial.kernel.library import LIBRARY, batch_score, collatz, mandelbrot, waves

needs_metal = pytest.mark.skipif(not metal.available(), reason="no Metal")


def test_generated_sources_have_expected_shape():
    msl, cu = mandelbrot.to_metal(), mandelbrot.to_cuda_c()
    assert "kernel void mandelbrot" in msl and "thread_position_in_grid" in msl
    assert '__global__ void mandelbrot' in cu and "blockIdx" in cu
    assert "while" in msl and "while" in cu
    tl_src = mandelbrot.to_triton()
    assert "@triton.jit" in tl_src and "def mandelbrot(" in tl_src and "tl.program_id" in tl_src and "while" in tl_src


def test_cpu_matches_plain_python_for_collatz():
    out = collatz.run("cpu", 8, limit=200)
    def ref(x, lim):
        k = 0
        while x != 1 and k < lim:
            x = x // 2 if x % 2 == 0 else 3 * x + 1
            k += 1
        return k
    assert all(out[i, j] == ref(i * 8 + j + 1, 200) for i in range(8) for j in range(8))


def test_cpu_mandelbrot_is_plausible():
    out = mandelbrot.run("cpu", 64, iters=50)
    assert out.min() >= 1 and out.max() == 50 and (out == 50).sum() > 100     # the set has an inside


@needs_metal
def test_integer_kernel_is_bit_identical_cpu_vs_metal():
    a, b = collatz.run("cpu", 64, limit=300), collatz.run("metal", 64, limit=300)
    assert np.array_equal(a, b)


@needs_metal
def test_float_kernels_agree_within_tolerance():
    a, b = mandelbrot.run("cpu", 128, iters=100), mandelbrot.run("metal", 128, iters=100)
    assert np.mean(a != b) < 0.01                 # float32 chaos at the set's boundary: a few pixels may differ
    w1, w2 = waves.run("cpu", 64, terms=8), waves.run("metal", 64, terms=8)
    assert np.abs(w1.astype(np.int64) - w2.astype(np.int64)).max() <= 3     # GPU sin/cos differ in the last bits
    r1, r2 = batch_score.run("cpu", 64, signals=16), batch_score.run("metal", 64, signals=16)
    assert np.abs(r1.astype(np.int64) - r2.astype(np.int64)).max() <= 5


def test_unsupported_constructs_are_refused():
    with pytest.raises(KernelError):
        @kernel
        def bad(i: int, j: int, n: int):
            return [1][0]
    with pytest.raises(KernelError):
        @kernel
        def bad2(i: int, j: int, n: int):
            x = open("/etc/passwd")
            return 1
    with pytest.raises(KernelError):
        @kernel
        def bad3(i: int, j: int, n: int, q):
            return 1
    with pytest.raises(KernelError):
        @kernel
        def bad4(i: int, j: int, n: int):
            return 1.5 % 2
    with pytest.raises(KernelError):
        @kernel
        def bad5(i: int, j: int, n: int):
            return undefined_name


def test_cuda_backend_refuses_to_pretend():
    with pytest.raises(KernelError):
        mandelbrot.run("cuda", 8, iters=10)


def test_triton_backend_refuses_to_pretend_and_has_no_reduction():
    for dev in ("run", "reduce"):
        with pytest.raises(KernelError, match="triton"):
            getattr(mandelbrot, dev)("triton", 8, iters=10)
    with pytest.raises(TypeError):
        collatz.to_triton(reduce=True)


def test_triton_source_handles_ints_floats_and_control_flow_syntactically():
    src = collatz.to_triton()
    assert "import triton" in src and "import triton.language as tl" in src
    assert "tl.store(out_ptr + i * n + j" in src and ".to(tl.uint32)" in src
    assert ").to(tl.int32)" in src                                      # the // floor-vs-truncate cast
    compile(src, "<triton collatz>", "exec")                            # at least syntactically valid Python
    msl = mandelbrot.to_triton()
    assert "while" in msl and "tl.program_id" in msl
    compile(msl, "<triton mandelbrot>", "exec")
    w = waves.to_triton()
    assert "tl.sin" in w and "tl.cos" in w
    compile(w, "<triton waves>", "exec")


def test_library_complete():
    assert set(LIBRARY) == {"mandelbrot", "collatz", "waves", "batch_score"}


def test_batch_score_is_a_plausible_probability_and_matches_cpu_metal():
    out = batch_score.run("cpu", 64, signals=16)
    assert out.min() >= 0 and out.max() <= 10000 and out.std() > 0           # quantised probability, not a constant
    tl = batch_score.to_triton()
    assert "@triton.jit" in tl and "while" in tl and "tl.exp" in tl
    compile(tl, "<triton batch_score>", "exec")



def test_planner_offers_portable_kernel_families():
    from spatial.unified import Job, Objective, Planner
    pl = Planner()
    plan = pl.plan(Job.compute("pk_collatz", n=64, limit=100), Objective())
    names = {o.name for o in plan.options}
    assert "cpu" in names and plan.chosen is not None
    ex = pl.execute(plan)
    assert ex.result == int(collatz.run("cpu", 64, limit=100).astype("uint64").sum())


@pytest.mark.parametrize("vertical", ["rtb", "credit", "claims", "alerts", "moderation", "telecom"])
def test_vertical_families_are_the_same_kernel_as_batch_score_under_a_market_name(vertical):
    """rtb/credit/claims/alerts/moderation/telecom are presentation names for ONE kernel (batch_score):
    same math, same code, no per-vertical model. A result that differs would mean someone duplicated and
    drifted the logic instead of reusing it."""
    from spatial.compute import workloads as w
    from spatial.unified import Job, Objective, Planner
    direct = getattr(w, f"pk_{vertical}_cpu")(64, 16)
    assert direct == batch_score.run("cpu", 64, signals=16).astype("uint64").sum()
    pl = Planner()
    plan = pl.plan(Job.compute(f"pk_{vertical}", n=64, signals=16), Objective())
    assert "cpu" in {o.name for o in plan.options} and plan.chosen is not None
    assert pl.execute(plan).result == direct


@needs_metal
def test_int32_overflow_matches_between_cpu_and_metal():
    # the 3x+1 map overflows 32 bits for large starts: CPU must wrap like the GPU does
    a, b = collatz.run("cpu", 512, limit=1000), collatz.run("metal", 512, limit=1000)
    assert np.array_equal(a, b)


@pytest.mark.parametrize("n", [16, 37, 100])
def test_cpu_reduction_equals_the_sum_of_the_map(n):
    assert collatz.reduce("cpu", n, limit=300) == int(collatz.run("cpu", n, limit=300).astype("uint64").sum())


@needs_metal
@pytest.mark.parametrize("n", [16, 37, 100, 256])
def test_metal_reduction_in_shared_memory_is_exact_for_integer_kernels(n):
    assert collatz.reduce("metal", n, limit=300) == collatz.reduce("cpu", n, limit=300)     # sizes that are not multiples of 16 included


@needs_metal
def test_metal_reduction_of_a_float_kernel_is_close():
    a, b = mandelbrot.reduce("cpu", 128, iters=100), mandelbrot.reduce("metal", 128, iters=100)
    assert abs(a - b) / a < 0.01


def test_reduction_sources_use_shared_memory_and_barriers_and_hip_has_its_header():
    assert "threadgroup ulong _sp_sh[256]" in collatz.to_metal(reduce=True) and "threadgroup_barrier" in collatz.to_metal(reduce=True)
    cu = collatz.to_cuda_c(reduce=True)
    assert "__shared__ unsigned long long _sp_sh[256]" in cu and "__syncthreads" in cu and "collatz_sum" in cu
    hip = collatz.to_hip(reduce=True)
    assert hip.startswith("#include <hip/hip_runtime.h>") and "__global__" in hip
    assert "hip" not in collatz.to_cuda_c()
    for dev in ("cuda", "hip"):
        with pytest.raises(KernelError):
            collatz.reduce(dev, 8, limit=10)


def test_names_that_would_clash_with_generated_code_are_refused():
    with pytest.raises(KernelError, match="reserved"):
        @kernel
        def bad(i: int, j: int, n: int):
            out = 1
            return out
    with pytest.raises(KernelError, match="reserved"):
        @kernel
        def bad2(i: int, j: int, n: int, total: int):
            return 1
    with pytest.raises(KernelError, match="reserved"):
        @kernel
        def bad3(i: int, j: int, n: int):
            tl = 1
            return tl

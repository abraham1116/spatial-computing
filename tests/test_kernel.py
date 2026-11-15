"""Portable kernels: same source, same result on CPU and Metal; unsupported code is refused."""
import numpy as np
import pytest

from spatial.fabric import metal
from spatial.kernel import KernelError, kernel
from spatial.kernel.library import LIBRARY, collatz, mandelbrot, waves

needs_metal = pytest.mark.skipif(not metal.available(), reason="no Metal")


def test_generated_sources_have_expected_shape():
    msl, cu = mandelbrot.to_metal(), mandelbrot.to_cuda_c()
    assert "kernel void mandelbrot" in msl and "thread_position_in_grid" in msl
    assert '__global__ void mandelbrot' in cu and "blockIdx" in cu
    assert "while" in msl and "while" in cu


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


def test_library_complete():
    assert set(LIBRARY) == {"mandelbrot", "collatz", "waves"}


def test_planner_offers_portable_kernel_families():
    from spatial.unified import Job, Objective, Planner
    pl = Planner()
    plan = pl.plan(Job.compute("pk_collatz", n=64, limit=100), Objective())
    names = {o.name for o in plan.options}
    assert "cpu" in names and plan.chosen is not None
    ex = pl.execute(plan)
    assert ex.result == int(collatz.run("cpu", 64, limit=100).astype("uint64").sum())


@needs_metal
def test_int32_overflow_matches_between_cpu_and_metal():
    # the 3x+1 map overflows 32 bits for large starts: CPU must wrap like the GPU does
    a, b = collatz.run("cpu", 512, limit=1000), collatz.run("metal", 512, limit=1000)
    assert np.array_equal(a, b)

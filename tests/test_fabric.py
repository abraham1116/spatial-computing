"""Virtual accelerator fabric: one job, several devices, chosen by measured cost."""
import pytest

from spatial.compute import workloads
from spatial.core.ledger import Ledger
from spatial.fabric import discover, metal
from spatial.unified import Job, Objective, Planner, Prices

needs_metal = pytest.mark.skipif(not metal.available(), reason="no Metal GPU (macOS with swiftc)")


@pytest.fixture
def planner(tmp_path):
    return Planner(ledger=Ledger(tmp_path / "plan.jsonl"))


def test_discovery_always_reports_the_cpu_and_never_pretends_about_nvidia():
    ds = {d.id: d for d in discover()}
    assert ds["cpu"].available and ds["cpu"].backend == "numba"
    nv = [d for d in ds.values() if d.vendor == "NVIDIA"]
    assert nv and all((not d.available) or d.backend == "cuda" for d in nv)


def test_cuda_variant_is_rejected_with_the_reason_when_there_is_no_nvidia_gpu(planner):
    from spatial.fabric import cuda
    if cuda.available():
        pytest.skip("a real CUDA device is present: covered by the hardware test A2")
    plan = planner.plan(Job.compute("mandel_f32", n=64, iters=50))
    gpu = next(o for o in plan.options if o.name == "gpu_cuda")
    assert not gpu.feasible and "NVIDIA" in gpu.reason and plan.chosen.name != "gpu_cuda"
    with pytest.raises(RuntimeError, match="no CUDA device"):
        workloads.mandel_f32_cuda(64, 50)


@needs_metal
def test_same_job_on_cpu_and_gpu_agrees_and_the_planner_picks_the_really_faster_device(planner):
    import time
    ref = workloads.mandel_f32_cpu(256, 120)
    assert abs(ref - workloads.mandel_f32_metal(256, 120)) / ref < 1e-3          # both devices compute the same thing
    for n, iters in ((32, 100), (2048, 200)):
        plan = planner.plan(Job.compute("mandel_f32", n=n, iters=iters))
        real = {}
        for o in plan.options:
            if o.feasible:
                o.run()                                                           # warm
                best = float("inf")
                for _ in range(3):
                    t0 = time.perf_counter()
                    o.run()
                    best = min(best, time.perf_counter() - t0)
                real[o.name] = best
        # machine-independent property: whatever device wins HERE, the planner's choice must be near the real best
        assert real[plan.chosen.name] <= 1.5 * min(real.values()), (n, real, plan.chosen.name)
    ex = planner.execute(plan)
    assert abs(ex.result - workloads.mandel_f32_cpu(2048, 200)) / ex.result < 1e-3
    assert abs(ex.time_error_pct) < 400                # one run: process start-up jitter; accuracy is measured in bench_unified.py


@needs_metal
def test_device_prices_change_the_choice(planner):
    pricey = Planner(prices=Prices(device_usd_h={"gpu_metal": 1e6}), ledger=planner.ledger)
    assert pricey.plan(Job.compute("mandel_f32", n=2048, iters=200)).chosen.name == "cpu"       # GPU too dear to rent
    gpu = next(o for o in pricey.plan(Job.compute("mandel_f32", n=2048, iters=200)).options if o.name == "gpu_metal")
    assert gpu.est_cost_usd > 1000 * next(o for o in pricey.plan(Job.compute("mandel_f32", n=2048, iters=200)).options if o.name == "cpu").est_cost_usd

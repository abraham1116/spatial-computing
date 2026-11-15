import pytest

from spatial.compute import detect_node, limitations, snapshot, workloads
from spatial.compute.cost import CostModel
from spatial.compute.scheduler import ComputeScheduler
from spatial.compute.worker import LocalWorkerProcess
from spatial.core.ledger import Ledger
from spatial.core.model import ResourceKind


def test_detect_reports_real_hardware():
    n = detect_node()
    cpu = n.by_kind(ResourceKind.CPU)[0]
    ram = n.by_kind(ResourceKind.RAM)[0]
    assert cpu.capacity >= 1 and ram.capacity > 1 << 30
    # swap must never be classified as RAM
    assert all("NOT RAM" in r.name for r in n.by_kind(ResourceKind.FAR_MEMORY))
    assert isinstance(limitations(n), list)


def test_snapshot_fields():
    s = snapshot()
    assert 0 <= s["cpu_percent"] <= 100 and s["ram_available"] <= s["ram_total"]


def test_workload_variants_agree():
    ref = workloads.mandel_python(48, 60)
    assert workloads.mandel_numpy(48, 60) == ref
    if workloads.HAVE_NUMBA:
        assert workloads.mandel_numba(48, 60) == ref
        assert workloads.mandel_numba_parallel(48, 60) == ref
        assert workloads.mandel_numba(48, 60, 0, 20) + workloads.mandel_numba(48, 60, 20, 48) == ref


def test_unknown_workload_is_refused():
    with pytest.raises(KeyError):
        workloads.run("not_a_registered_workload", x=1)


def test_scheduler_compares_and_chooses(tmp_path):
    with LocalWorkerProcess() as w:
        c = w.client()
        s = ComputeScheduler(detect_node(), Ledger(tmp_path / "l.jsonl"), c)
        s.warmup()
        rows = s.compare("t", {"n": 96, "iters": 80}, s.mandel_strategies())
        assert all(r.ok for r in rows), [(r.strategy, r.notes) for r in rows if not r.ok]
        assert all(r.metrics["matches_reference"] for r in rows)
        best = s.choose(rows, "time")
        assert best.strategy != "local_python"
        with pytest.raises(RuntimeError):      # worker also refuses non-whitelisted work
            c.call({"op": "run", "workload": "nope", "params": {}})
        c.close()


def test_cost_model_labels_estimates():
    cm = CostModel()
    loc = cm.local(wall_s=10, energy_j=200, idle_watts=8)
    assert loc["estimated"] is False and loc["marginal_energy_j"] == pytest.approx(120)
    cl = cm.cloud("aws_c7i_large", local_wall_s=10, speed_ratio=1.0)
    assert cl["estimated"] is True and cl["billed_s"] == 60   # minimum billing dominates short jobs
    assert cl["total_usd"] > loc["total_usd"]

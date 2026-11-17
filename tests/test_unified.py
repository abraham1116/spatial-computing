"""One objective for every engine: options are priced the same way, ranked by one function,
executed, and the estimate is checked against reality."""
from pathlib import Path

import pytest

from spatial.compute import workloads
from spatial.core import auth
from spatial.core.ledger import Ledger
from spatial.core.protocol import RpcClient
from spatial.fleet import Agent, serve_hub
from spatial.unified import Job, Objective, PlanError, Planner, Prices

BUILD = Path(__file__).resolve().parents[1] / "benchmarks" / "build"


@pytest.fixture
def planner(tmp_path):
    return Planner(ledger=Ledger(tmp_path / "plan.jsonl"))


def test_every_engine_family_is_registered_and_variants_agree():
    from spatial.unified.providers import FAMILIES
    for fam in FAMILIES.values():
        assert all(w in workloads.REGISTRY for w in fam["variants"].values())


def test_compute_plan_prefers_the_cheapest_correct_variant_and_estimates_hold(planner):
    job = Job.compute("mandel", n=700, iters=250)
    plan = planner.plan(job)
    names = [o.name for o in plan.options]
    assert set(names) == {"python", "numpy", "numba_jit", "numba_threads"} and all(o.feasible for o in plan.options)
    assert plan.chosen.name.startswith("numba") and plan.options[0] is plan.chosen
    costs = [o.est_cost_usd for o in plan.options if o.feasible]
    assert costs == sorted(costs)                                          # ranked by the one objective
    ex = planner.execute(plan)
    assert ex.result == workloads.mandel_numba(700, 250)                   # same answer as the reference
    assert abs(ex.time_error_pct) < 100                                    # estimate within a factor of 2 of reality
    assert ex.actual_cost_usd == pytest.approx(ex.wall_s / 3600 * planner.prices.local_usd_per_hour)
    rows = [r for r in planner.ledger.rows("measurement") if r["engine"] == "planner"]
    assert rows and "est_time_s" in rows[-1]["metrics"] and planner.ledger.verify() == (True, None)


def test_calibration_loop_corrects_future_estimates(planner):
    job = Job.compute("pk_batch_score", n=64, signals=16)
    first = planner.plan(job).chosen
    assert "calibrated" not in first.basis
    for _ in range(3):
        planner.execute(planner.plan(job))
    later = planner.plan(job).chosen
    assert "calibrated(" in later.basis and later.key == first.key


def test_constraints_reject_with_reasons_and_can_leave_no_option(planner):
    with pytest.raises(PlanError, match="deadline"):
        planner.plan(Job.compute("mandel", n=900, iters=300), Objective(deadline_s=1e-6))
    plan = planner.plan(Job.dataset(24 << 30, 50000), Objective(max_ram_bytes=1 << 30))
    assert plan.chosen.name == "tiered_ssd" and plan.chosen.est_ram_bytes == 1 << 30
    inram = next(o for o in plan.options if o.name == "in_ram")
    assert not inram.feasible and "RAM" in inram.reason


def test_dataset_choice_flips_with_size_and_is_validated_at_reduced_scale(planner):
    assert planner.plan(Job.dataset(4 << 20, 20000)).chosen.name == "in_ram"
    big = planner.plan(Job.dataset(40 << 30, 20000))
    assert big.chosen.name == "tiered_ssd" and 0 < big.chosen.meta["hit_ratio"] < 1
    small_budget = planner.plan(Job.dataset(512 << 20, 20000), Objective(max_ram_bytes=64 << 20))
    ex = planner.execute(small_budget)
    r = ex.result
    assert r["validated_scale"] < 1 and r["accesses"] > 0 and 0 < r["predicted_hit_ratio"] < 1
    assert abs(ex.time_error_pct) < 300                                    # model and real store agree to the right order


def test_kv_cache_restore_versus_recompute_depends_on_reuse_and_is_exact(planner):
    assert planner.plan(Job.kv_cache(1500, 0.0)).chosen.est_time_s == 0       # never reused: nothing to pay
    likely = planner.plan(Job.kv_cache(1500, 0.9))
    assert likely.chosen.name == "restore"
    ex = planner.execute(likely)
    assert ex.result["logits_equal_to_full_recompute"] is True
    priced = Planner(prices=Prices(storage_usd_gb_hour=1e6), ledger=planner.ledger)      # absurdly dear storage
    assert priced.plan(Job.kv_cache(1500, 0.9)).chosen.name == "recompute"


needs_bins = pytest.mark.skipif(not (BUILD / "bench-linux.elf").exists(), reason="run benchmarks first to build the binaries")


@needs_bins
def test_runtime_routes_are_priced_and_isolation_is_a_constraint(planner):
    job = Job.binary(str(BUILD / "bench-linux.elf"), ["64", "50"], est_native_s=0.05)
    plan = planner.plan(job)
    assert {o.name for o in plan.options if o.feasible} >= {"microvm-hvf", "microvm-tcg"}
    assert plan.chosen.name == "microvm-hvf"                               # cheaper than software emulation
    assert int(planner.execute(plan).result.split()[1]) == workloads.mandel_python(64, 50)
    mac = Job.binary(str(BUILD / "bench-macos"), ["64", "50"], est_native_s=0.05)
    assert planner.plan(mac).chosen.name == "native"
    with pytest.raises(PlanError, match="does not isolate"):                # a macOS binary has no isolated route here
        planner.plan(mac, Objective(require_isolation=True))


def test_fleet_nodes_are_options_priced_at_their_own_rate_and_really_execute(tmp_path):
    az = auth.Authorizer(b"u" * 32, Ledger(tmp_path / "audit.jsonl"))
    srv, hub = serve_hub(authorizer=az, ledger=Ledger(tmp_path / "dec.jsonl"))
    srv.start()
    tok = lambda n, s: az.issue(n, s).encode()
    cheap = Agent("127.0.0.1", srv.port, tok("cheap", ["fleet:report", "fleet:work"]), interval_s=0.3, poll_s=0.1, usd_per_hour=0.001).start()
    noprice = Agent("127.0.0.1", srv.port, tok("noprice", ["fleet:report", "fleet:work"]), interval_s=0.3, poll_s=0.1).start()
    ops = RpcClient("127.0.0.1", srv.port, tok("ops", ["fleet:read", "fleet:submit"]), timeout=60)
    try:
        import time
        t = time.time()
        while time.time() - t < 20 and len([r for r in hub.node_table(30) if r["samples"] >= 1]) < 2:
            time.sleep(0.1)
        pl = Planner(ledger=Ledger(tmp_path / "plan.jsonl"), hub=ops)
        job = Job.compute("mandel", n=300, iters=200)
        plan = pl.plan(job)
        by = {o.key: o for o in plan.options}
        assert by["fleet/cheap"].feasible and "price unknown" in by["fleet/noprice"].reason
        assert plan.chosen.key == "fleet/cheap"                              # 0.001 $/h beats the local 0.134 $/h
        assert pl.execute(plan).result == workloads.mandel_numba(300, 200)    # executed on the node, identical result
        assert hub.task(max(hub.tasks))["node"] == "cheap"
        local_only = pl.plan(job, Objective(allow_remote=False))
        assert local_only.chosen.engine == "compute"
        assert not next(o for o in local_only.options if o.key == "fleet/cheap").feasible
    finally:
        cheap.stop(); noprice.stop(); ops.close(); srv.stop()

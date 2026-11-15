"""Fleet: hub logic on injected measurements, then real agents over the encrypted protocol."""
import socket
import time

import pytest

from spatial.compute import workloads
from spatial.core import auth
from spatial.core.ledger import Ledger
from spatial.core.protocol import RpcClient
from spatial.fleet import Agent, Hub, serve_hub

GB = 2 ** 30


class Clock:
    def __init__(self): self.t = 1_000_000.0
    def __call__(self): return self.t


def feed(hub, name, cpu, cores=4, ram_free_pct=60, gpus=None, price=None, n=5, clk=None, ram_total=16 * GB):
    for i in range(n):
        ts = clk.t - (n - 1 - i) * 5
        hub.report(name, {"ts": ts, "cpu_percent": cpu, "cpu_count": cores, "load1": 1.0, "ram_total": ram_total,
                          "ram_available": ram_total * ram_free_pct / 100, "swap_used": 0, "memory_pressure": "normal",
                          "gpus": gpus or []}, usd_per_hour=price)


def kinds(recs):
    return [r["kind"] for r in recs]


def test_advice_rebalance_and_consolidation_with_savings():
    clk = Clock(); hub = Hub(clock=clk)
    feed(hub, "a", 95, price=2.0, clk=clk); feed(hub, "b", 5, price=2.0, clk=clk); feed(hub, "c", 5, price=2.0, clk=clk)
    recs = hub.advise()
    assert "rebalance" in kinds(recs)
    reb = next(r for r in recs if r["kind"] == "rebalance")
    assert reb["node"] == "a" and reb["to"] in ("b", "c")
    con = next(r for r in recs if r["kind"] == "consolidate")
    assert len(con["nodes_to_free"]) == 1 and con["est_saving_usd_per_hour"] == pytest.approx(2.0)
    assert con["est_saving_usd_per_month"] == pytest.approx(1460.0)
    assert con["evidence"]["busy_cores"] == pytest.approx(0.95 * 4 + 0.05 * 8) and "assumes" in con["evidence"]
    u = hub.utilization()
    assert u["cores"] == 12 and u["cpu_utilization_pct"] == pytest.approx(100 * (0.95 * 4 + 0.4) / 12)


def test_no_advice_when_the_measurements_do_not_justify_it():
    clk = Clock(); hub = Hub(clock=clk)
    feed(hub, "a", 55, clk=clk); feed(hub, "b", 60, clk=clk)
    assert hub.advise() == []                               # balanced and well used: say nothing
    feed(hub, "c", 5, n=2, clk=clk); feed(hub, "d", 99, n=2, clk=clk)
    assert all(r.get("node") not in ("c", "d") for r in hub.advise())      # fewer than 3 samples: no conclusion


def test_consolidation_refuses_when_memory_would_not_fit_and_flags_gpus_pressure_and_down_nodes():
    clk = Clock(); hub = Hub(clock=clk)
    feed(hub, "a", 5, ram_free_pct=20, clk=clk); feed(hub, "b", 5, ram_free_pct=20, clk=clk)     # tiny CPU load, RAM 80% used
    assert "consolidate" not in kinds(hub.advise())
    feed(hub, "g", 50, gpus=[{"name": "T4", "util": 3, "vram_total": 16 * GB, "vram_used": 0}], price=0.5, clk=clk)
    feed(hub, "m", 50, ram_free_pct=4, clk=clk)
    recs = hub.advise()
    assert {"gpu_underused", "memory_pressure"} <= set(kinds(recs))
    clk.t += 120
    assert next(r for r in hub.advise() if r["kind"] == "node_down")["severity"] == "high"
    assert not any(r["alive"] for r in hub.node_table()) and hub.utilization()["nodes"] == 0


def test_buffered_reports_keep_their_time_and_the_future_is_clamped():
    clk = Clock(); hub = Hub(clock=clk)
    hub.report("a", {"ts": clk.t - 50, "cpu_percent": 10, "cpu_count": 2, "ram_total": GB, "ram_available": GB // 2})
    hub.report("a", {"ts": clk.t + 9999, "cpu_percent": 20, "cpu_count": 2, "ram_total": GB, "ram_available": GB // 2})
    ts = [t for t, _ in hub.series["a"]]
    assert ts[0] == clk.t - 50 and ts[1] == clk.t


def test_placement_respects_needs_backpressure_and_priority():
    clk = Clock(); hub = Hub(clock=clk)
    feed(hub, "cpu1", 20, clk=clk); feed(hub, "gpu1", 20, gpus=[{"name": "A", "util": 0, "vram_total": 1, "vram_used": 0}], clk=clk)
    feed(hub, "hot", 97, clk=clk)
    with pytest.raises(KeyError):
        hub.submit("not_allowed", {})
    low = hub.submit("montecarlo_pi", {"samples": 10}, priority=9)
    hi = hub.submit("montecarlo_pi", {"samples": 10}, priority=1)
    needs_gpu = hub.submit("montecarlo_pi", {"samples": 10}, needs={"gpu": True})
    pinned = hub.submit("montecarlo_pi", {"samples": 10}, needs={"node": "gpu1"}, priority=0)
    assert hub.poll("hot") is None                                    # saturated node gets nothing
    assert hub.poll("nobody") is None
    assert hub.poll("cpu1")["id"] == hi                               # pinned task is not for it; best priority wins
    assert hub.poll("cpu1")["id"] == low
    assert hub.poll("gpu1")["id"] == pinned and hub.poll("gpu1")["id"] == needs_gpu
    assert hub.poll("gpu1") is None
    with pytest.raises(PermissionError):
        hub.result("cpu1", pinned, True, 1)                           # a node cannot finish another node's task


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def wait(pred, timeout=30):
    t = time.time()
    while time.time() - t < timeout:
        if pred():
            return True
        time.sleep(0.1)
    return False


def test_real_agents_over_the_encrypted_protocol_scopes_identity_and_audit(tmp_path):
    az = auth.Authorizer(b"f" * 32, Ledger(tmp_path / "audit.jsonl"))
    srv, hub = serve_hub(authorizer=az, ledger=Ledger(tmp_path / "decisions.jsonl"))
    srv.start()
    tok = lambda name, scopes: az.issue(name, scopes).encode()
    agents = [Agent("127.0.0.1", srv.port, tok(f"node-{i}", ["fleet:report", "fleet:work"]), name=f"spoof-{i}",
                    interval_s=0.3, poll_s=0.1, usd_per_hour=1.0).start() for i in range(2)]
    ops = RpcClient("127.0.0.1", srv.port, tok("ops", ["fleet:submit", "fleet:read"]), timeout=30)
    try:
        assert wait(lambda: len([r for r in hub.node_table(30) if r["samples"] >= 2]) == 2)
        assert {r["node"] for r in hub.node_table()} == {"node-0", "node-1"}       # identity = credential, not self-declared name
        ids = [ops.call({"op": "submit", "workload": "mandel_numba", "params": {"n": 200, "iters": 150}})[0]["task_id"] for _ in range(8)]
        assert wait(lambda: all(hub.task(i)["state"] == "done" for i in ids), 60)
        ref = workloads.mandel_numba(200, 150)
        assert all(hub.task(i)["result"] == ref for i in ids)                      # distributed results equal the reference
        assert sum(a.tasks_done for a in agents) == 8
        rows = ops.call({"op": "nodes"})[0]
        assert len(rows["nodes"]) == 2 and rows["utilization"]["nodes"] == 2
        assert all(isinstance(r, dict) for r in ops.call({"op": "advise"})[0]["recommendations"])
        with pytest.raises(RuntimeError, match="PermissionError.*fleet:report"):   # a reader cannot inject measurements
            ops.call({"op": "report", "metrics": {"cpu_percent": 1}})
        ag = RpcClient("127.0.0.1", srv.port, tok("node-9", ["fleet:report", "fleet:work"]), timeout=30)
        with pytest.raises(RuntimeError, match="PermissionError.*fleet:read"):     # an agent cannot read the fleet
            ag.call({"op": "nodes"})
        with pytest.raises(RuntimeError, match="PermissionError.*fleet:submit"):
            ag.call({"op": "submit", "workload": "mandel_numba", "params": {}})
        ag.close()
    finally:
        for a in agents:
            a.stop()
        ops.close(); srv.stop()
    audit = [r for r in Ledger(tmp_path / "audit.jsonl").rows("decision") if r["engine"] == "auth"]
    assert any(r["decision"] == "ops:report" and r["reason"].startswith("denied") for r in audit)
    assert Ledger(tmp_path / "audit.jsonl").verify() == (True, None)
    assert Ledger(tmp_path / "decisions.jsonl").verify() == (True, None)
    assert len(Ledger(tmp_path / "decisions.jsonl").rows("decision")) == 8       # every placement is on record


def test_agent_buffers_while_the_hub_is_down_and_delivers_on_reconnect():
    port = _free_port()
    agent = Agent("127.0.0.1", port, b"tok", name="lonely", interval_s=0.3, run_tasks=False).start()
    try:
        assert wait(lambda: agent.last_error is not None, 10) and agent.sent == 0
        time.sleep(1.2)                                              # a few measurements pile up in the buffer
        srv, hub = serve_hub(b"tok", port=port)
        srv.start()
        try:
            assert wait(lambda: len(hub.series.get("lonely", ())) >= 4, 20) and agent.last_error is None
            stamps = [t for t, _ in hub.series["lonely"]]
            assert stamps == sorted(stamps) and stamps[0] < time.time() - 1.0        # old measurements kept their own time
        finally:
            srv.stop()
    finally:
        agent.stop()


def test_fair_share_gives_the_idle_tenant_the_next_slot_and_honours_weights():
    clk = Clock(); hub = Hub(clock=clk)
    feed(hub, "n1", 10, clk=clk)
    a = [hub.submit("montecarlo_pi", {"samples": 1}, tenant="A") for _ in range(4)]
    b = [hub.submit("montecarlo_pi", {"samples": 1}, tenant="B") for _ in range(2)]
    order = []
    for _ in range(6):
        t = hub.poll("n1"); order.append(hub.task(t["id"])["tenant"])
        clk.t += 10; hub.result("n1", t["id"], True, 0, wall_s=10)
    assert order[:4] == ["A", "B", "A", "B"]                       # alternates while both have work: A cannot starve B
    assert order[4:] == ["A", "A"]                                 # B is out of work, A takes the rest
    # weights: B counts double, so it gets about two slots for each of A's
    hub2 = Hub(clock=clk); feed(hub2, "n1", 10, clk=clk); hub2.set_weight("B", 2)
    for _ in range(6): hub2.submit("montecarlo_pi", {"samples": 1}, tenant="A"); hub2.submit("montecarlo_pi", {"samples": 1}, tenant="B")
    got = []
    for _ in range(9):
        t = hub2.poll("n1"); got.append(hub2.task(t["id"])["tenant"]); clk.t += 10; hub2.result("n1", t["id"], True, 0, wall_s=10)
    assert got.count("B") == 6 and got.count("A") == 3
    with pytest.raises(ValueError):
        hub.set_weight("A", 0)
    assert {r["tenant"] for r in hub.tenants()} == {"A", "B"}


def test_gang_starts_only_when_every_member_can_and_holds_the_other_nodes():
    clk = Clock(); hub = Hub(clock=clk, gang_hold_s=30)
    feed(hub, "n1", 10, clk=clk); feed(hub, "n2", 10, clk=clk)
    g = hub.submit_gang("montecarlo_pi", [{"samples": 1}] * 3)       # needs 3 nodes, only 2 exist
    assert hub.poll("n1") is None and hub.poll("n2") is None         # all-or-nothing: nothing starts
    feed(hub, "n3", 10, clk=clk)
    first = hub.poll("n1")
    assert first and hub.task(first["id"])["gang"] == g["gang"]
    lone = hub.submit("montecarlo_pi", {"samples": 1}, priority=0)   # a better-priority task must not steal a held node
    assert hub.poll("n2")["id"] in g["tasks"] and hub.poll("n3")["id"] in g["tasks"]
    assert hub.task(lone)["state"] == "queued"


def test_a_held_node_is_released_when_the_gang_does_not_complete():
    clk = Clock(); hub = Hub(clock=clk, gang_hold_s=30)
    for n in ("a", "b", "c"):
        feed(hub, n, 10, clk=clk)
    hub.submit_gang("montecarlo_pi", [{"samples": 1}] * 3)
    assert hub.poll("a") is not None                                  # starts, holds b and c
    only = hub.submit("montecarlo_pi", {"samples": 1}, priority=0)
    assert hub.poll("b") is not None and hub.task(only)["state"] == "queued"      # b serves its gang, not the lone task
    clk.t += 31                                                       # c never polled: the hold on c expires
    assert hub.poll("c")["id"] == only


def test_cache_affinity_prefers_the_node_that_holds_the_cache_then_gives_up_waiting():
    clk = Clock(); hub = Hub(clock=clk, affinity_wait_s=5)
    feed(hub, "n1", 10, clk=clk); feed(hub, "n2", 10, clk=clk)
    t1 = hub.submit("montecarlo_pi", {"samples": 1}, needs={"affinity": "prompt-42"})
    assert hub.poll("n1")["id"] == t1
    hub.result("n1", t1, True, 0, wall_s=1)                           # n1 now holds the cache for this key
    feed(hub, "n1", 10, clk=clk); feed(hub, "n2", 10, clk=clk)
    t2 = hub.submit("montecarlo_pi", {"samples": 1}, needs={"affinity": "prompt-42"})
    assert hub.poll("n2") is None                                     # n1 is free: n2 waits
    assert hub.poll("n1")["id"] == t2
    hub.result("n1", t2, True, 0, wall_s=1)
    t3 = hub.submit("montecarlo_pi", {"samples": 1}, needs={"affinity": "prompt-42"})
    clk.t += 6; feed(hub, "n1", 10, clk=clk); feed(hub, "n2", 10, clk=clk)
    assert hub.poll("n2")["id"] == t3                                 # after the wait, anyone may take it


def test_snapshot_restore_requeues_running_tasks_and_accepts_a_late_result(tmp_path):
    clk = Clock(); hub = Hub(clock=clk)
    feed(hub, "n1", 10, clk=clk)
    hub.set_weight("B", 2)
    done = hub.submit("montecarlo_pi", {"samples": 1}, tenant="A")
    t = hub.poll("n1"); hub.result("n1", t["id"], True, 3.14, wall_s=2.0)
    running = hub.submit("montecarlo_pi", {"samples": 1}, tenant="B"); hub.poll("n1")
    queued = hub.submit("montecarlo_pi", {"samples": 1}, tenant="A")
    path = tmp_path / "hub.json"
    hub.save(path)
    assert not (tmp_path / "hub.json.tmp").exists()
    new = Hub(clock=clk)
    info = new.load(path)
    assert info == {"tasks": 3, "queued": 2, "requeued_running": 1}
    assert new.task(done)["state"] == "done" and new.task(done)["result"] == 3.14
    assert new.usage["A"] == 2.0 and new.weights["B"] == 2.0              # fair-share history survives
    assert new.submit("montecarlo_pi", {"samples": 1}) > queued              # ids never repeat
    feed(new, "n1", 10, clk=clk)
    new.result("n1", running, True, 1.0, wall_s=1.0)                         # the old agent finished it after all
    assert new.task(running)["state"] == "done" and running not in new.queue
    assert Hub().load(tmp_path / "missing.json") is None


def test_hub_restart_on_the_same_port_agents_reconnect_and_queued_work_survives(tmp_path):
    port = _free_port()
    path = tmp_path / "state.json"
    srv, hub = serve_hub(b"tok", port=port); srv.start()
    ids = [hub.submit("montecarlo_pi", {"samples": 2000, "seed": i}) for i in range(4)]
    hub.save(path)
    srv.stop()                                                               # the hub dies with 4 tasks queued
    agent = Agent("127.0.0.1", port, b"tok", name="a1", interval_s=0.3).start()
    try:
        assert wait(lambda: agent.last_error is not None, 10)                # the agent notices
        t0 = time.time()
        srv2, hub2 = serve_hub(b"tok", port=port)
        assert hub2.load(path)["queued"] == 4
        srv2.start()
        try:
            assert wait(lambda: all(hub2.task(i)["state"] == "done" for i in ids), 40)
            assert time.time() - t0 < 30                                      # reconnect plus four tasks
        finally:
            srv2.stop()
    finally:
        agent.stop()

"""Hub high availability: promotion, state following, split-brain resolution, agent failover."""
import socket
import time

import pytest

from spatial.fleet import Agent, Hub, serve_hub
from spatial.fleet.ha import HAController, connect_active

TOK = b"ha-secret"


def port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Clock:
    t = 1000.0
    def __call__(self): return self.t


def pair(clk):
    pa, pb = port(), port()
    sa, ha = serve_hub(TOK, port=pa); sb, hb = serve_hub(TOK, port=pb)
    sa.start(); sb.start()
    ca = HAController(ha, TOK, [f"127.0.0.1:{pb}"], "a", clock=clk, fail_after_s=6)
    cb = HAController(hb, TOK, [f"127.0.0.1:{pa}"], "b", clock=clk, fail_after_s=6)
    return (sa, ha, ca, pa), (sb, hb, cb, pb)


def test_promotion_following_failover_and_demotion_of_the_returning_hub():
    clk = Clock()
    (sa, ha, ca, pa), (sb, hb, cb, pb) = pair(clk)
    try:
        assert ca.step() == "standby"                         # nobody active yet, but not silent long enough
        clk.t += 7
        assert ca.step() == "active" and ha.epoch == 2        # silence for 7 s: a takes over
        assert cb.step() == "standby"                         # b sees an active peer and follows it
        ids = [ha.submit("montecarlo_pi", {"samples": 5}, tenant="T") for _ in range(3)]
        cb.step()
        assert sorted(hb.tasks) == sorted(ids) and hb.epoch == 2
        with pytest.raises(RuntimeError, match="standby"):    # a standby refuses real work
            from spatial.core.protocol import RpcClient
            RpcClient("127.0.0.1", pb, TOK).call({"op": "nodes"})
        sa.stop()                                             # the active hub dies
        clk.t += 3
        assert cb.step() == "standby"                         # 3 s of silence: not yet
        clk.t += 4
        assert cb.step() == "active" and hb.epoch == 3        # 7 s: b promotes, state preserved
        assert [hb.task(i)["state"] for i in ids] == ["queued"] * 3
        # a returns with its stale state, must NOT stay active
        sa2, ha2 = serve_hub(TOK, port=pa, hub=ha); sa2.start()
        try:
            assert ca.step() == "standby" and ha.role == "standby"
        finally:
            sa2.stop()
    finally:
        sb.stop()


def test_split_brain_with_equal_epochs_the_larger_name_steps_down():
    clk = Clock()
    (sa, ha, ca, pa), (sb, hb, cb, pb) = pair(clk)
    try:
        ha.role = hb.role = "active"; ha.epoch = hb.epoch = 5
        ha.submit("montecarlo_pi", {"samples": 1}); hb.submit("montecarlo_pi", {"samples": 1}); hb.submit("montecarlo_pi", {"samples": 1})
        assert ca.step() == "active"                          # a (smaller name) keeps the role
        assert cb.step() == "standby"                         # b steps down and adopts a's state
        assert len(hb.tasks) == 1                             # its divergent tasks were discarded: documented
        sa.stop(); sb.stop()
    finally:
        pass


def test_agent_fails_over_to_the_new_active_hub_and_work_completes():
    pa, pb = port(), port()
    sa, ha = serve_hub(TOK, port=pa); sb, hb = serve_hub(TOK, port=pb)
    sa.start(); sb.start()
    ca = HAController(ha, TOK, [f"127.0.0.1:{pb}"], "a", poll_s=0.2, fail_after_s=1.0).start()
    cb = HAController(hb, TOK, [f"127.0.0.1:{pa}"], "b", poll_s=0.2, fail_after_s=1.0).start()
    hubs = f"127.0.0.1:{pa},127.0.0.1:{pb}"
    agent = None
    try:
        deadline = time.time() + 15
        while time.time() < deadline and (ha.role, hb.role).count("active") != 1:   # both may promote at once; the tie-break settles it
            time.sleep(0.1)
        assert (ha.role, hb.role).count("active") == 1
        cli = connect_active(hubs, TOK)
        ids = [cli.call({"op": "submit", "workload": "montecarlo_pi", "params": {"samples": 3000, "seed": i}})[0]["task_id"] for i in range(3)]
        cli.close()
        time.sleep(0.6)                                       # let the standby copy the queue
        active_srv, standby_hub = (sa, hb) if ha.role == "active" else (sb, ha)
        active_srv.stop()                                     # kill the active hub before any agent exists
        agent = Agent(hubs, None, TOK, name="n1", interval_s=0.3, poll_s=0.2).start()
        deadline = time.time() + 40
        while time.time() < deadline and not all(standby_hub.tasks.get(i, {}).get("state") == "done" for i in ids):
            time.sleep(0.2)
        assert standby_hub.role == "active"
        assert all(standby_hub.tasks[i]["state"] == "done" for i in ids)
    finally:
        if agent:
            agent.stop()
        ca.stop(); cb.stop()
        for s in (sa, sb):
            try: s.stop()
            except Exception: pass

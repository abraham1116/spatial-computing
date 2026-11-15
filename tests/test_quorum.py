"""Quorum election for 3+ hubs: one leader per term, lease, majority needed, partition behaviour."""
import random
import socket

import pytest

from spatial.core.protocol import RpcClient
from spatial.fleet import serve_hub
from spatial.fleet.ha import QuorumController, connect_active

TOK = b"quorum-secret"


def port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Clock:
    t = 5000.0
    def __call__(self): return self.t


def cluster(n=3, clk=None, fail_after=6.0):
    clk = clk or Clock()
    ports = [port() for _ in range(n)]
    nodes = []
    for i in range(n):
        srv, hub = serve_hub(TOK, port=ports[i]); srv.start()
        peers = [f"127.0.0.1:{p}" for j, p in enumerate(ports) if j != i]
        nodes.append({"srv": srv, "hub": hub, "ctl": QuorumController(hub, TOK, peers, f"h{i}", clock=clk, fail_after_s=fail_after), "port": ports[i], "up": True})
    return clk, nodes


def leaders(nodes):
    return [x for x in nodes if x["ctl"].state == "leader"]


def run(clk, nodes, rounds, dt=1.0):
    for _ in range(rounds):
        clk.t += dt
        for x in nodes:
            if x["up"]:
                x["ctl"].step()


def kill(x):
    x["srv"].stop(); x["up"] = False; x["ctl"].offline = True


def revive(x):
    srv, _ = serve_hub(TOK, port=x["port"], hub=x["hub"]); srv.start()
    x["srv"], x["up"] = srv, True; x["ctl"].offline = False


def test_exactly_one_leader_is_elected_and_the_others_follow_its_state():
    clk, nodes = cluster()
    try:
        run(clk, nodes, 20)
        ls = leaders(nodes)
        assert len(ls) == 1 and ls[0]["hub"].role == "active"
        assert all(x["hub"].role == "standby" for x in nodes if x is not ls[0])
        assert len({x["ctl"].term for x in nodes}) == 1
        ids = [ls[0]["hub"].submit("montecarlo_pi", {"samples": 1}) for _ in range(3)]
        run(clk, nodes, 3)
        for x in nodes:
            assert sorted(x["hub"].tasks) == sorted(ids)                    # followers copied the leader's tasks
        addrs = ",".join(f"127.0.0.1:{x['port']}" for x in nodes)
        cli = connect_active(addrs, TOK)
        assert cli.call({"op": "role"})[0]["name"] == ls[0]["ctl"].name
    finally:
        for x in nodes:
            x["srv"].stop()


def test_leader_failure_elects_a_new_leader_with_the_state_and_old_leader_rejoins_as_follower():
    clk, nodes = cluster()
    try:
        run(clk, nodes, 20)
        old = leaders(nodes)[0]
        ids = [old["hub"].submit("montecarlo_pi", {"samples": 1}) for _ in range(2)]
        run(clk, nodes, 3)
        kill(old)
        run(clk, nodes, 25)
        new = leaders([x for x in nodes if x is not old])
        assert len(new) == 1 and new[0]["ctl"].term > old["ctl"].term - 0
        assert sorted(new[0]["hub"].tasks) == sorted(ids)
        revive(old)
        run(clk, nodes, 10)
        assert len(leaders(nodes)) == 1 and old["ctl"].state == "follower" and old["hub"].role == "standby"
    finally:
        for x in nodes:
            x["srv"].stop()


def test_a_leader_cut_off_from_the_majority_stops_serving_then_steps_down_while_the_others_elect():
    clk, nodes = cluster(fail_after=6.0)
    try:
        run(clk, nodes, 20)
        old = leaders(nodes)[0]
        others = [x for x in nodes if x is not old]
        old["ctl"].offline = True                                             # cut off in both directions
        old["srv"].stop(); old["up"] = False
        # the isolated leader still believes it leads, but its lease (3 s without a majority) expires first
        for _ in range(4):
            clk.t += 1.0
            old["ctl"].step()
        assert old["ctl"].state == "leader" and not old["ctl"].lease_ok()
        with pytest.raises(RuntimeError, match="no quorum"):
            from spatial.fleet.hub import make_handler
            make_handler(old["hub"])({"op": "nodes"}, b"")
        run(clk, others, 25)
        assert len(leaders(others)) == 1
        for _ in range(8):                                                    # it keeps stepping on its own: 6 s without majority
            clk.t += 1.0
            old["ctl"].step()
        assert old["ctl"].state == "follower"
    finally:
        for x in nodes:
            try: x["srv"].stop()
            except Exception: pass


def test_no_leader_without_a_majority():
    clk, nodes = cluster()
    try:
        run(clk, nodes, 20)
        l = leaders(nodes)[0]
        for x in nodes:
            if x is not l:
                kill(x)
        run(clk, [l], 15)                                                     # alone: one of three
        assert l["ctl"].state != "leader" or not l["ctl"].lease_ok()
    finally:
        for x in nodes:
            try: x["srv"].stop()
            except Exception: pass


def test_a_candidate_behind_on_tasks_cannot_win_and_a_vote_is_given_once_per_term(tmp_path):
    clk, nodes = cluster()
    try:
        run(clk, nodes, 20)
        l = leaders(nodes)[0]
        for _ in range(3):
            l["hub"].submit("montecarlo_pi", {"samples": 1})
        run(clk, nodes, 2)
        v = next(x for x in nodes if x is not l)
        t = v["ctl"].term + 1
        c = RpcClient("127.0.0.1", v["port"], TOK)
        assert c.call({"op": "vote", "term": t, "candidate": "x", "last_id": 0})[0]["granted"] is False       # behind: refused
        assert c.call({"op": "vote", "term": t, "candidate": "y", "last_id": 99})[0]["granted"] is True
        assert c.call({"op": "vote", "term": t, "candidate": "z", "last_id": 99})[0]["granted"] is False      # already voted in t
        assert c.call({"op": "vote", "term": t, "candidate": "y", "last_id": 99})[0]["granted"] is True       # same candidate again: idempotent
    finally:
        for x in nodes:
            x["srv"].stop()


def test_term_and_vote_survive_a_restart(tmp_path):
    clk = Clock()
    srv, hub = serve_hub(TOK, port=port())
    ctl = QuorumController(hub, TOK, ["127.0.0.1:1", "127.0.0.1:2"], "z", clock=clk, meta_path=str(tmp_path / "m.term"))
    ctl.on_vote({"term": 7, "candidate": "q", "last_id": 0})
    hub2 = srv.handler and serve_hub(TOK, port=port())[1]
    ctl2 = QuorumController(hub2, TOK, ["127.0.0.1:1", "127.0.0.1:2"], "z", clock=clk, meta_path=str(tmp_path / "m.term"))
    assert ctl2.term == 7 and ctl2.voted_for == "q"
    assert ctl2.on_vote({"term": 7, "candidate": "other", "last_id": 0})["granted"] is False


def test_safety_under_random_crashes_and_partitions_never_two_leaders_in_one_term():
    rng = random.Random(21)
    clk, nodes = cluster(5, fail_after=4.0)
    leaders_seen: dict[int, set] = {}
    try:
        for rnd in range(220):
            if rng.random() < 0.12:
                x = rng.choice(nodes)
                (revive if not x["up"] else kill)(x)
            run(clk, nodes, 1, dt=rng.choice([0.5, 1.0, 2.0]))
            for x in nodes:
                if x["ctl"].state == "leader":
                    leaders_seen.setdefault(x["ctl"].term, set()).add(x["ctl"].name)
        assert leaders_seen, "no leader was ever elected"
        assert all(len(v) == 1 for v in leaders_seen.values()), leaders_seen          # election safety
    finally:
        for x in nodes:
            try: x["srv"].stop()
            except Exception: pass

"""Hub high availability: one active hub, standby hubs that follow it, automatic promotion.

What it is: active/standby replication by polling. The standby pulls the active hub's state (op
`snapshot`, scope fleet:replicate) every `poll_s` seconds. If no active hub answers for
`fail_after_s`, the standby promotes itself (epoch + 1, running tasks requeued). Agents and clients
take a list of hub addresses and use the one that says it is active.

What it is NOT: consensus. There is no quorum and no leader lease. Under a network partition two hubs
can both be active for a while; when they see each other again the one with the lower epoch (or, at
equal epoch, the larger name) steps down and DISCARDS its divergent state. Tasks that ran on the
losing side may run twice (workloads are pure, so that is safe) and results recorded only there are
lost. Up to `poll_s` of state is lost at a failover. Use an odd-numbered quorum system (etcd, Raft)
when that is not acceptable.
"""
from __future__ import annotations

import json
import os
import threading
import time
import zlib

from ..core.protocol import RpcClient


def parse_addrs(spec: str | list) -> list[tuple[str, int]]:
    """'h1:7700,h2:7700' -> [('h1', 7700), ('h2', 7700)]."""
    items = spec.split(",") if isinstance(spec, str) else spec
    out = []
    for it in items:
        if isinstance(it, tuple):
            out.append(it)
            continue
        host, _, port = it.strip().rpartition(":")
        out.append((host or "127.0.0.1", int(port)))
    return out


def connect_active(addrs, token: bytes, timeout: float = 30.0) -> RpcClient:
    """Connect to the first address whose hub reports itself active. Raises ConnectionError if none does."""
    errors = []
    for host, port in parse_addrs(addrs):
        try:
            cli = RpcClient(host, port, token, timeout=timeout)
        except (OSError, ConnectionError) as e:
            errors.append(f"{host}:{port} {type(e).__name__}")
            continue
        try:
            r = cli.call({"op": "role"})[0]
            if r.get("role") == "active" and r.get("lease", True):
                return cli
            errors.append(f"{host}:{port} standby")
        except (OSError, ConnectionError, RuntimeError) as e:
            errors.append(f"{host}:{port} {e}")
        cli.close()
    raise ConnectionError("no active hub: " + "; ".join(errors))


class HAController:
    def __init__(self, hub, token: bytes, peers, name: str, poll_s: float = 1.0, fail_after_s: float = 6.0,
                 clock=time.time, on_change=None):
        self.hub, self.token, self.peers = hub, token, parse_addrs(peers)
        self.poll_s, self.fail_after_s, self.clock, self.on_change = poll_s, fail_after_s, clock, on_change
        hub.name = name
        hub.role = "standby"                                 # start passive; promotion needs fail_after_s of silence
        self._since = clock()                                # when we last saw an active peer (or started)
        self._stop = threading.Event()
        self.last_error: str | None = None

    def _peer(self, addr) -> tuple[dict | None, RpcClient | None]:
        try:
            cli = RpcClient(addr[0], addr[1], self.token, timeout=max(2.0, self.poll_s * 3))
            return cli.call({"op": "role"})[0], cli
        except (OSError, ConnectionError, RuntimeError) as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return None, None

    def _beats(self, role: dict) -> bool:
        """Does the peer outrank us? Higher epoch wins; at equal epoch the smaller name stays active."""
        mine = (self.hub.epoch, self.hub.name)
        theirs = (int(role["epoch"]), role["name"])
        return theirs[0] > mine[0] or (theirs[0] == mine[0] and theirs[1] < mine[1])

    def step(self) -> str:
        """One round: returns the role after it. Called by the thread; callable directly in tests."""
        hub, now = self.hub, self.clock()
        active_peer = None
        for addr in self.peers:
            role, cli = self._peer(addr)
            if role is None:
                continue
            if role["role"] == "active" and (hub.role == "standby" or self._beats(role)):
                active_peer = cli
                break
            cli.close()
        if hub.role == "active":
            if active_peer is not None:                      # a better active hub exists: step down, adopt its state
                hub.role = "standby"
                self._since = now
                self._follow(active_peer)
                self._changed("demoted")
            return hub.role
        if active_peer is not None:
            self._follow(active_peer)
            self._since = now
        elif now - self._since >= self.fail_after_s:         # nobody active for long enough: take over
            hub.epoch += 1
            hub.requeue_running()
            hub.role = "active"
            self._changed("promoted")
        return hub.role

    def _follow(self, cli: RpcClient) -> None:
        try:
            _, blob = cli.call({"op": "snapshot"})
            self.hub.restore(json.loads(blob), requeue=False)
        except (OSError, ConnectionError, RuntimeError, ValueError) as e:
            self.last_error = f"{type(e).__name__}: {e}"
        finally:
            cli.close()

    def _changed(self, what: str) -> None:
        if self.hub.ledger:
            self.hub.ledger.decide("fleet", f"hub {self.hub.name} {what}", f"epoch {self.hub.epoch}")
        if self.on_change:
            self.on_change(what, self.hub)

    def start(self) -> "HAController":
        def loop():
            while not self._stop.wait(self.poll_s):
                try:
                    self.step()
                except Exception as e:                       # never let the monitor die
                    self.last_error = f"{type(e).__name__}: {e}"
        threading.Thread(target=loop, daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()


class QuorumController:
    """Three or more hubs, one leader chosen by majority vote (Raft-style terms and votes).

    What it guarantees: at most ONE leader per term, and a leader serves requests only while it has heard
    from a majority within the last `fail_after_s / 2` (a lease), so a hub cut off from the others stops
    answering before a new leader can be elected (given clocks that tick at about the same rate). A hub
    restarted with its term file does not vote twice in a term.
    What it does not give: a replicated log. State travels by snapshot polling from the leader, so a
    failover can lose up to one poll of recent changes; a candidate whose newest task id is older than a
    voter's cannot win. This is election safety, not linearizable storage. Not a Raft implementation.
    """

    def __init__(self, hub, token: bytes, peers, name: str, poll_s: float = 1.0, fail_after_s: float = 6.0,
                 clock=time.time, meta_path: str | None = None, on_change=None):
        self.hub, self.token, self.peers = hub, token, parse_addrs(peers)
        self.poll_s, self.fail_after_s, self.clock, self.on_change = poll_s, fail_after_s, clock, on_change
        self.name, self.meta_path = name, meta_path
        self.majority = (len(self.peers) + 1) // 2 + 1
        jitter = (zlib.crc32(name.encode()) % 1000) / 1000                  # spreads elections so they rarely collide
        self.timeout = fail_after_s * (1 + jitter)
        self.term, self.voted_for, self.state = 0, None, "follower"
        self.last_beat = self.last_majority = clock()
        self.offline = False                                                 # tests: behave as a hub cut off from the network
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self.last_error: str | None = None
        hub.name, hub.role, hub.ha = name, "standby", self
        self._load()
        hub.epoch = self.term

    # ------------------------------------------------------------------ persistence of term and vote
    def _load(self):
        if self.meta_path and os.path.exists(self.meta_path):
            try:
                m = json.load(open(self.meta_path))
                self.term, self.voted_for = int(m["term"]), m.get("voted_for")
            except (OSError, ValueError, KeyError):
                pass

    def _persist(self):
        if self.meta_path:
            tmp = self.meta_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"term": self.term, "voted_for": self.voted_for}, f); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, self.meta_path)

    # ------------------------------------------------------------------ state changes
    def lease_ok(self) -> bool:
        if self.state != "leader":
            return True
        return self.clock() - self.last_majority < self.fail_after_s / 2

    def _follower(self, term: int):
        with self._lock:
            if term > self.term:
                self.term, self.voted_for = term, None
            self.state = "follower"
            self.hub.role, self.hub.epoch = "standby", self.term
            self._persist()

    def _changed(self, what: str):
        if self.hub.ledger:
            self.hub.ledger.decide("fleet", f"hub {self.name} {what}", f"term {self.term}")
        if self.on_change:
            self.on_change(what, self.hub)

    # ------------------------------------------------------------------ handlers for peers
    def on_vote(self, h: dict) -> dict:
        if self.offline:
            raise ConnectionError("offline")
        with self._lock:
            term, cand = int(h["term"]), str(h["candidate"])
            if term > self.term:
                self._follower(term)
            fresh = int(h.get("last_id", 0)) >= self.hub.last_id()           # candidate must not be behind us
            grant = term == self.term and self.voted_for in (None, cand) and fresh
            if grant:
                self.voted_for, self.last_beat = cand, self.clock()
                self._persist()
            return {"granted": grant, "term": self.term}

    def on_beat(self, h: dict) -> dict:
        if self.offline:
            raise ConnectionError("offline")
        with self._lock:
            term = int(h["term"])
            if term < self.term:
                return {"ok": False, "term": self.term}
            if term > self.term or self.state != "follower":
                self._follower(term)
            self.last_beat = self.clock()
            return {"ok": True, "term": self.term}

    # ------------------------------------------------------------------ outbound
    def _try(self, addr, header: dict):
        if self.offline:
            return None
        try:
            cli = RpcClient(addr[0], addr[1], self.token, timeout=max(2.0, self.poll_s * 3))
            try:
                return cli.call(header)[0]
            finally:
                cli.close()
        except (OSError, ConnectionError, RuntimeError) as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return None

    def _pull(self):
        for addr in self.peers:
            if self.offline:
                return
            try:
                cli = RpcClient(addr[0], addr[1], self.token, timeout=max(2.0, self.poll_s * 3))
            except (OSError, ConnectionError):
                continue
            try:
                r = cli.call({"op": "role"})[0]
                if r["role"] == "active" and int(r["epoch"]) == self.term:
                    _, blob = cli.call({"op": "snapshot"})
                    with self._lock:
                        if self.state == "follower":
                            self.hub.restore(json.loads(blob), requeue=False)
                            self.hub.epoch = self.term
                    return
            except (OSError, ConnectionError, RuntimeError, ValueError):
                pass
            finally:
                cli.close()

    # ------------------------------------------------------------------ one round
    def step(self) -> str:
        now = self.clock()
        if self.state == "leader":
            acks, higher = 1, None
            for addr in self.peers:
                r = self._try(addr, {"op": "beat", "term": self.term, "name": self.name})
                if r is None:
                    continue
                if r["term"] > self.term:
                    higher = r["term"]
                elif r["ok"]:
                    acks += 1
            if higher is not None:
                self._follower(higher); self.last_beat = now; self._changed("stepped down (higher term)")
            elif acks >= self.majority:
                self.last_majority = now
            elif now - self.last_majority >= self.fail_after_s:
                self._follower(self.term); self.last_beat = now; self._changed("stepped down (lost majority)")
            return self.state
        if now - self.last_beat < self.timeout:
            self._pull()
            return self.state
        # no leader heard for a full timeout: stand for election
        with self._lock:
            self.term += 1
            self.voted_for, self.state = self.name, "candidate"
            self.hub.epoch = self.term
            self._persist()
            term = self.term
        votes = 1
        for addr in self.peers:
            r = self._try(addr, {"op": "vote", "term": term, "candidate": self.name, "last_id": self.hub.last_id()})
            if r is None:
                continue
            if r["term"] > term:
                self._follower(r["term"]); self.last_beat = now
                return self.state
            if r["granted"]:
                votes += 1
        with self._lock:
            if self.state == "candidate" and self.term == term and votes >= self.majority and not self.offline:
                self.state = "leader"
                self.hub.role = "active"
                self.hub.requeue_running()
                self.last_majority = self.clock()
                self._changed("elected")
            else:
                self.state = "follower"
                self.last_beat = now                                          # back off for another timeout
        return self.state

    def start(self) -> "QuorumController":
        def loop():
            while not self._stop.wait(self.poll_s):
                try:
                    self.step()
                except Exception as e:
                    self.last_error = f"{type(e).__name__}: {e}"
        threading.Thread(target=loop, daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()

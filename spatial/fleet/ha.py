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
import threading
import time

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
            if cli.call({"op": "role"})[0].get("role") == "active":
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

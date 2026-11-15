"""Fleet hub: nodes, time series, task queue, placement and recommendations.

Scopes (scoped credentials, see core/auth.py):
  fleet:report  an agent sends its measurements
  fleet:work    an agent polls for tasks and posts results
  fleet:submit  a client submits tasks and reads their results
  fleet:read    a client reads nodes, recommendations and utilization
With scoped credentials a node's identity is the credential name: an agent cannot report as
another node. With a plain shared token the agent's self-declared name is used.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import math
import threading
import time
from collections import deque
from pathlib import Path

from ..compute import workloads
from ..core import auth
from ..core.auth import authorizer_from_file, require
from ..core.ledger import Ledger
from ..core.protocol import RpcServer

HISTORY = 2000          # samples kept per node


class Hub:
    def __init__(self, ledger: Ledger | None = None, stale_after_s: float = 30.0, clock=time.time,
                 busy_cpu_pct: float = 90.0, gang_hold_s: float = 30.0, affinity_wait_s: float = 5.0,
                 max_finished: int = 5000, max_affinity: int = 10000):
        self.nodes: dict[str, dict] = {}
        self.series: dict[str, deque] = {}
        self.tasks: dict[int, dict] = {}
        self.queue: deque[int] = deque()
        self.ledger = ledger
        self.stale_after_s = stale_after_s
        self.clock = clock
        self.busy_cpu_pct = busy_cpu_pct
        self._ids = itertools.count(1)
        self._lock = threading.RLock()
        self.gang_hold_s = gang_hold_s              # how long idle nodes are held for a gang that has started
        self.affinity_wait_s = affinity_wait_s      # how long a task waits for the node that holds its cache
        self.weights: dict[str, float] = {}         # tenant -> share weight (default 1)
        self.usage: dict[str, float] = {}           # tenant -> finished compute-seconds
        self.gangs: dict[int, dict] = {}
        self.affinity: dict[str, str] = {}          # cache key -> node that last ran it
        self.role = "active"                        # "standby": answers only ping and role (see fleet/ha.py)
        self.epoch = 1                              # raised at every promotion; the higher epoch wins a split brain
        self.name = "hub"
        self.ha = None                              # a fleet.ha controller, if any
        self.max_finished, self.max_affinity = max_finished, max_affinity   # bounded memory: the soak test showed the hub grew without limit
        self._finished: deque = deque()             # ids of done/failed tasks, oldest first

    # ------------------------------------------------------------------ identity
    @staticmethod
    def _who(header: dict) -> str:
        p = auth.current()
        name = p.name if p is not None else header.get("node")
        if not name or not isinstance(name, str) or len(name) > 128:
            raise ValueError("a node name is required")
        return name

    # ------------------------------------------------------------------ ops
    def report(self, node: str, metrics: dict, inventory: dict | None = None, usd_per_hour: float | None = None,
               labels: list | None = None) -> None:
        now = self.clock()
        ts = min(float(metrics.get("ts", now)), now)            # a buffered report keeps its own time, never the future
        with self._lock:
            n = self.nodes.setdefault(node, {"first_seen": now})
            n["last_seen"] = now
            if inventory is not None:
                n["inventory"] = inventory
            if usd_per_hour is not None:
                n["usd_per_hour"] = float(usd_per_hour)
            if labels is not None:
                n["labels"] = list(labels)[:16]
            m = {k: metrics.get(k) for k in ("cpu_percent", "cpu_count", "load1", "ram_total", "ram_available",
                                              "swap_used", "memory_pressure", "gpus")}
            n["latest"] = {**m, "ts": ts}
            self.series.setdefault(node, deque(maxlen=HISTORY)).append((ts, m))

    def submit(self, workload: str, params: dict, needs: dict | None = None, priority: int = 10,
               tenant: str = "default", _gang: int | None = None) -> int:
        if workload not in workloads.REGISTRY:
            raise KeyError(f"workload '{workload}' is not allow-listed")
        with self._lock:
            tid = next(self._ids)
            self.tasks[tid] = {"id": tid, "workload": workload, "params": params, "needs": needs or {},
                               "priority": int(priority), "state": "queued", "submitted": self.clock(),
                               "tenant": str(tenant), "gang": _gang}
            self.queue.append(tid)
            return tid

    def submit_gang(self, workload: str, params_list: list[dict], needs: dict | None = None, priority: int = 10,
                    tenant: str = "default") -> dict:
        """All-or-nothing group: the members start only when enough eligible idle nodes exist for ALL of
        them; the first start holds the other nodes for `gang_hold_s`. Admission and reservation, not
        preemption: a member that already runs is never stopped."""
        if not params_list:
            raise ValueError("a gang needs at least one member")
        with self._lock:
            gid = next(self._ids)
            tids = [self.submit(workload, p, {**(needs or {}), "distinct_nodes": True}, priority, tenant, _gang=gid) for p in params_list]
            self.gangs[gid] = {"id": gid, "size": len(tids), "tasks": tids, "reserved": {}, "started": [], "tenant": str(tenant)}
            return {"gang": gid, "tasks": tids}

    def set_weight(self, tenant: str, weight: float) -> None:
        if not weight > 0:
            raise ValueError("weight must be positive")
        with self._lock:
            self.weights[str(tenant)] = float(weight)

    def _tenant_load(self, tenant: str, now: float) -> float:
        """Weighted compute-seconds consumed so far (finished plus running): lowest goes first."""
        running = sum(now - t.get("started", now) for t in self.tasks.values() if t["state"] == "running" and t["tenant"] == tenant)
        return (self.usage.get(tenant, 0.0) + running) / self.weights.get(tenant, 1.0)

    def queue_view(self, recent: int = 12) -> dict:
        """Counts per state plus the most recent tasks (no parameters or results: those can be large)."""
        with self._lock:
            counts: dict[str, int] = {}
            for t in self.tasks.values():
                counts[t["state"]] = counts.get(t["state"], 0) + 1
            last = sorted(self.tasks.values(), key=lambda t: t["id"], reverse=True)[:recent]
            return {"counts": counts, "recent": [{k: t.get(k) for k in ("id", "workload", "state", "node", "tenant", "gang", "wall_s")} for t in last]}

    def tenants(self) -> list[dict]:
        with self._lock:
            now = self.clock()
            names = sorted({t["tenant"] for t in self.tasks.values()} | set(self.weights))
            return [{"tenant": n, "weight": self.weights.get(n, 1.0), "finished_s": self.usage.get(n, 0.0),
                     "weighted_load": self._tenant_load(n, now),
                     "queued": sum(1 for t in self.tasks.values() if t["tenant"] == n and t["state"] == "queued"),
                     "running": sum(1 for t in self.tasks.values() if t["tenant"] == n and t["state"] == "running")} for n in names]

    def _eligible(self, node: str, needs: dict) -> bool:
        n = self.nodes.get(node)
        if not n or "latest" not in n:
            return False
        lat = n["latest"]
        if needs.get("node") and needs["node"] != node:
            return False
        if needs.get("label") and needs["label"] not in n.get("labels", []):
            return False
        if needs.get("gpu") and not lat.get("gpus"):
            return False
        if needs.get("min_ram_gb") and (lat.get("ram_available") or 0) < needs["min_ram_gb"] * 2 ** 30:
            return False
        return True

    def _ready(self, node: str, now: float) -> bool:
        """Fresh, not saturated, not running a task."""
        n = self.nodes.get(node)
        if not n or "latest" not in n or now - n.get("last_seen", 0) > self.stale_after_s:
            return False
        if (n["latest"].get("cpu_percent") or 0) >= self.busy_cpu_pct:
            return False
        return not any(t["state"] == "running" and t.get("node") == node for t in self.tasks.values())

    def _gang_nodes(self, g: dict, needs: dict, now: float, exclude: str) -> list[str]:
        """Other ready, eligible nodes not held by a different gang."""
        held = {nd for og in self.gangs.values() if og["id"] != g["id"] for nd, exp in og["reserved"].items() if exp > now}
        return sorted(nd for nd in self.nodes if nd != exclude and nd not in held and nd not in g["started"]
                      and self._ready(nd, now) and self._eligible(nd, needs))

    def poll(self, node: str) -> dict | None:
        """Hand the best eligible queued task to an agent that asks for work. Backpressure: a node that
        reports itself saturated gets nothing. Order: tenant with the lowest weighted usage first (fair
        share), then priority, then submission order. Gang members start only when the whole gang can;
        a task with a cache-affinity key waits `affinity_wait_s` for the node that holds that cache."""
        with self._lock:
            n = self.nodes.get(node)
            if not n or "latest" not in n:
                return None
            if (n["latest"].get("cpu_percent") or 0) >= self.busy_cpu_pct:
                return None
            now = self.clock()
            for g in self.gangs.values():
                g["reserved"] = {nd: exp for nd, exp in g["reserved"].items() if exp > now}
            for g in self.gangs.values():                    # a node held for a gang serves only that gang
                if node in g["reserved"]:
                    mine = [self.tasks[t] for t in g["tasks"] if t in self.tasks and self.tasks[t]["state"] == "queued" and self._eligible(node, self.tasks[t]["needs"])]
                    if not mine:
                        return None
                    return self._assign(min(mine, key=lambda t: t["id"]), node, now, g, "held for its gang")
            held_elsewhere = {nd for g in self.gangs.values() for nd, exp in g["reserved"].items() if exp > now}
            if node in held_elsewhere:
                return None
            load = {}
            best = None
            for tid in self.queue:
                t = self.tasks[tid]
                if not self._eligible(node, t["needs"]):
                    continue
                key = t["needs"].get("affinity")
                owner = self.affinity.get(key) if key else None
                if owner and owner != node and now - t["submitted"] < self.affinity_wait_s and self._ready(owner, now):
                    continue                                  # the node holding its cache is free: wait for it
                g = self.gangs.get(t["gang"]) if t["gang"] else None
                if g is not None:
                    missing = sum(1 for x in g["tasks"] if x in self.tasks and self.tasks[x]["state"] == "queued")
                    if len(self._gang_nodes(g, t["needs"], now, node)) + 1 < missing:
                        continue                              # not enough idle nodes for the whole gang yet
                tn = t["tenant"]
                if tn not in load:
                    load[tn] = self._tenant_load(tn, now)
                rank = (load[tn], 0 if owner == node else 1, t["priority"], tid)
                if best is None or rank < best[0]:
                    best = (rank, t, g)
            if best is None:
                return None
            _, t, g = best
            if g is not None and not g["started"]:
                for nd in self._gang_nodes(g, t["needs"], now, node)[: g["size"] - 1]:
                    g["reserved"][nd] = now + self.gang_hold_s
            return self._assign(t, node, now, g, "agent asked for work and is eligible")

    def _assign(self, t: dict, node: str, now: float, g: dict | None, why: str) -> dict:
        self.queue.remove(t["id"])
        t.update(state="running", node=node, started=now)
        if g is not None:
            g["started"].append(node)
            g["reserved"].pop(node, None)
        if self.ledger:
            self.ledger.decide("fleet", f"task {t['id']} -> {node}", why, workload=t["workload"], tenant=t["tenant"],
                               gang=t["gang"], node_cpu=(self.nodes[node]["latest"] or {}).get("cpu_percent"))
        return {"id": t["id"], "workload": t["workload"], "params": t["params"]}

    def result(self, node: str, task_id: int, ok: bool, value=None, error: str | None = None, wall_s: float | None = None):
        with self._lock:
            t = self.tasks.get(task_id)
            if t is None or t.get("node") != node:
                raise PermissionError("task is not assigned to this node")
            if t["state"] == "queued":                       # requeued after a hub restart, but its agent finished it anyway
                self.queue.remove(task_id)
            t.update(state="done" if ok else "failed", finished=self.clock(), result=value, error=error, wall_s=wall_s)
            self.usage[t["tenant"]] = self.usage.get(t["tenant"], 0.0) + (wall_s if wall_s is not None else self.clock() - t.get("started", self.clock()))
            if ok and t["needs"].get("affinity"):
                self.affinity.pop(t["needs"]["affinity"], None)
                self.affinity[t["needs"]["affinity"]] = node
                while len(self.affinity) > self.max_affinity:
                    self.affinity.pop(next(iter(self.affinity)))
            self._finished.append(task_id)
            while len(self._finished) > self.max_finished:     # forget the oldest finished tasks (and gangs with no task left)
                self.tasks.pop(self._finished.popleft(), None)
            if len(self.gangs) > 64:
                self.gangs = {k: g for k, g in self.gangs.items() if any(x in self.tasks for x in g["tasks"])}

    def task(self, task_id: int) -> dict:
        with self._lock:
            t = self.tasks.get(task_id)
            if t is None:
                raise KeyError(f"unknown task {task_id} (never existed, or finished long ago and was forgotten: the hub keeps the last {self.max_finished} finished tasks)")
            return {k: v for k, v in t.items()}


    # ------------------------------------------------------------------ persistence
    def snapshot(self) -> dict:
        """Durable state: tasks, queue order, tenant usage and weights, gangs, cache owners. Node
        measurements are not saved: agents rebuild them within one report interval."""
        with self._lock:
            return {"version": 1, "epoch": self.epoch, "next_id": next(self._ids), "tasks": list(self.tasks.values()), "queue": list(self.queue),
                    "usage": self.usage, "weights": self.weights, "affinity": self.affinity,
                    "gangs": [{**g, "reserved": {}} for g in self.gangs.values()]}

    def last_id(self) -> int:
        with self._lock:
            return max(self.tasks, default=0)

    def requeue_running(self) -> int:
        """Put running tasks back in the queue (at-least-once: the allow-listed workloads are pure
        functions); if the agent still finishes one, its result is accepted."""
        with self._lock:
            n = 0
            for t in self.tasks.values():
                if t["state"] == "running":
                    t["state"] = "queued"
                    t["requeued_after_restart"] = True
                    self.queue.append(t["id"])
                    n += 1
            return n

    def restore(self, snap: dict, requeue: bool = True) -> dict:
        """Load a snapshot (requeue=False for a standby that only follows the active hub)."""
        with self._lock:
            self.tasks = {int(t["id"]): t for t in snap["tasks"]}
            self.queue = deque(int(i) for i in snap["queue"])
            self.epoch = max(self.epoch, int(snap.get("epoch", 1)))
            self._finished = deque(t["id"] for t in sorted(self.tasks.values(), key=lambda t: t["id"]) if t["state"] in ("done", "failed"))
            requeued = self.requeue_running() if requeue else 0
            self.usage, self.weights, self.affinity = dict(snap["usage"]), dict(snap["weights"]), dict(snap["affinity"])
            self.gangs = {int(g["id"]): {**g, "started": [], "reserved": {}} for g in snap["gangs"]}
            self._ids = itertools.count(int(snap["next_id"]))
            return {"tasks": len(self.tasks), "queued": len(self.queue), "requeued_running": requeued}

    def save(self, path: str | Path) -> None:
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            json.dump(self.snapshot(), f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)                                # atomic: a crash leaves the old or the new file, never half

    def load(self, path: str | Path) -> dict | None:
        try:
            snap = json.loads(Path(path).read_text())
        except FileNotFoundError:
            return None
        return self.restore(snap)

    def autosave(self, path: str | Path, every_s: float = 5.0) -> threading.Event:
        """Save every `every_s` seconds in a daemon thread; set the returned event to stop (one last save is made)."""
        stop = threading.Event()

        def loop():
            while not stop.wait(every_s):
                try:
                    if self.role == "active":                # a standby holds a copy, never the master file
                        self.save(path)
                except OSError:
                    pass
            try:
                if self.role == "active":
                    self.save(path)
            except OSError:
                pass
        threading.Thread(target=loop, daemon=True).start()
        return stop

    # ------------------------------------------------------------------ views
    def _window(self, node: str, window_s: float, now: float) -> list:
        return [m for ts, m in self.series.get(node, ()) if now - window_s <= ts <= now]

    def node_table(self, window_s: float = 60.0) -> list[dict]:
        now = self.clock()
        rows = []
        with self._lock:
            for name, n in sorted(self.nodes.items()):
                w = self._window(name, window_s, now)
                lat = n.get("latest", {})
                age = now - n["last_seen"]
                gpus = [g for m in w for g in (m.get("gpus") or [])]
                rows.append({
                    "node": name, "alive": age <= self.stale_after_s, "age_s": age, "samples": len(w),
                    "cores": lat.get("cpu_count"), "cpu_avg": _avg([m["cpu_percent"] for m in w]),
                    "ram_total": lat.get("ram_total"),
                    "ram_avail_pct": _avg([100 * m["ram_available"] / m["ram_total"] for m in w if m.get("ram_total")]),
                    "gpu_count": len(lat.get("gpus") or []), "gpu_util_avg": _avg([g["util"] for g in gpus]),
                    "usd_per_hour": n.get("usd_per_hour"), "labels": n.get("labels", [])})
        return rows

    def utilization(self, window_s: float = 60.0) -> dict:
        """Fleet CPU utilization = busy cores / cores over the window (alive nodes with data only)."""
        rows = [r for r in self.node_table(window_s) if r["alive"] and r["samples"] and r["cores"]]
        cores = sum(r["cores"] for r in rows)
        busy = sum(r["cpu_avg"] / 100 * r["cores"] for r in rows)
        return {"nodes": len(rows), "cores": cores, "busy_cores": busy,
                "cpu_utilization_pct": 100 * busy / cores if cores else None}

    def advise(self, window_s: float = 60.0, idle_pct: float = 15.0, busy_pct: float = 80.0,
               target_pct: float = 60.0, min_samples: int = 3) -> list[dict]:
        """Recommendations with their evidence. Nothing is applied. Estimates assume the work can be
        moved and that the load pattern of the window continues; they are NOT measured savings."""
        rows = self.node_table(window_s)
        rec: list[dict] = []
        for r in rows:
            if not r["alive"]:
                rec.append({"kind": "node_down", "severity": "high", "node": r["node"],
                            "text": f"{r['node']} has been silent for {r['age_s']:.0f} s", "evidence": {"age_s": r["age_s"]}})
        ok = [r for r in rows if r["alive"] and r["samples"] >= min_samples and r["cores"]]
        for r in ok:
            if r["ram_avail_pct"] is not None and r["ram_avail_pct"] < 10:
                rec.append({"kind": "memory_pressure", "severity": "high", "node": r["node"],
                            "text": f"{r['node']} has only {r['ram_avail_pct']:.0f}% RAM available",
                            "evidence": {"ram_avail_pct": r["ram_avail_pct"]}})
            if r["gpu_count"] and r["gpu_util_avg"] is not None and r["gpu_util_avg"] < 20:
                rec.append({"kind": "gpu_underused", "severity": "medium", "node": r["node"],
                            "text": f"{r['node']}: {r['gpu_count']} GPU(s) at {r['gpu_util_avg']:.0f}% on average",
                            "evidence": {"gpu_util_avg": r["gpu_util_avg"], "gpus": r["gpu_count"]},
                            **({"est_cost_idle_usd_per_hour": r["usd_per_hour"]} if r["usd_per_hour"] else {})})
        busy = sorted((r for r in ok if r["cpu_avg"] >= busy_pct), key=lambda r: -r["cpu_avg"])
        idle = sorted((r for r in ok if r["cpu_avg"] <= idle_pct), key=lambda r: r["cpu_avg"])
        if busy and idle:
            rec.append({"kind": "rebalance", "severity": "medium", "node": busy[0]["node"], "to": idle[0]["node"],
                        "text": f"{busy[0]['node']} is at {busy[0]['cpu_avg']:.0f}% CPU while {idle[0]['node']} is at {idle[0]['cpu_avg']:.0f}%: move work from the first to the second",
                        "evidence": {"busy": busy[0]["cpu_avg"], "idle": idle[0]["cpu_avg"]}})
        if len(ok) >= 2:
            load = sum(r["cpu_avg"] / 100 * r["cores"] for r in ok)
            ram_used = sum((1 - (r["ram_avail_pct"] or 0) / 100) * (r["ram_total"] or 0) for r in ok)
            keep, cap, ram_cap = [], 0.0, 0.0
            for r in sorted(ok, key=lambda r: -r["cores"]):                      # keep the biggest nodes
                if cap >= load / (target_pct / 100) and ram_cap * 0.85 >= ram_used:
                    break
                keep.append(r)
                cap += r["cores"]
                ram_cap += r["ram_total"] or 0
            freed = [r for r in ok if r not in keep]
            if freed:
                prices = [r["usd_per_hour"] for r in freed if r["usd_per_hour"]]
                item = {"kind": "consolidate", "severity": "medium", "nodes_to_free": [r["node"] for r in freed],
                        "text": f"The fleet's load ({load:.1f} busy cores of {sum(r['cores'] for r in ok)}) would fit on {len(keep)} node(s) at {target_pct:.0f}% target utilization: {len(freed)} node(s) could be freed",
                        "evidence": {"busy_cores": load, "total_cores": sum(r["cores"] for r in ok), "kept": [r["node"] for r in keep],
                                     "assumes": "work is movable; memory checked at 85% of the kept nodes; load pattern continues"}}
                if len(prices) == len(freed):
                    item["est_saving_usd_per_hour"] = sum(prices)
                    item["est_saving_usd_per_month"] = sum(prices) * 730
                rec.append(item)
        return rec


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


# ---------------------------------------------------------------------- service
def _tenant(h: dict) -> str:
    """With scoped credentials the tenant is the credential name (it cannot be spoofed); otherwise the declared one."""
    p = auth.current()
    t = p.name if p is not None else h.get("tenant", "default")
    return str(t)[:128]


def make_handler(hub: Hub):
    def handle(h: dict, blob: bytes):
        op = h.get("op")
        if op == "ping":
            return {"pong": True}, b""
        if op == "role":
            return {"role": hub.role, "epoch": hub.epoch, "name": hub.name, "lease": hub.ha.lease_ok() if hub.ha else True}, b""
        if op in ("vote", "beat"):
            require("fleet:replicate")
            if not hasattr(hub.ha, "on_" + op):
                raise RuntimeError("this hub is not part of a quorum")
            return getattr(hub.ha, "on_" + op)(h), b""
        if hub.role != "active":
            raise RuntimeError(f"standby: {hub.name} is not the active hub")
        if hub.ha is not None and not hub.ha.lease_ok():
            raise RuntimeError("no quorum: this hub lost contact with a majority and refuses requests")
        if op == "snapshot":
            require("fleet:replicate")
            return {"epoch": hub.epoch}, json.dumps(hub.snapshot()).encode()
        if op == "report":
            require("fleet:report")
            hub.report(Hub._who(h), h["metrics"], h.get("inventory"), h.get("usd_per_hour"), h.get("labels"))
            return {}, b""
        if op == "poll":
            require("fleet:work")
            return {"task": hub.poll(Hub._who(h))}, b""
        if op == "result":
            require("fleet:work")
            hub.result(Hub._who(h), int(h["task_id"]), bool(h["ok"]), h.get("value"), h.get("error"), h.get("wall_s"))
            return {}, b""
        if op == "submit":
            require("fleet:submit")
            return {"task_id": hub.submit(h["workload"], h.get("params", {}), h.get("needs"), h.get("priority", 10), _tenant(h))}, b""
        if op == "submit_gang":
            require("fleet:submit")
            return hub.submit_gang(h["workload"], h["params_list"], h.get("needs"), h.get("priority", 10), _tenant(h)), b""
        if op == "queue":
            require("fleet:read")
            return hub.queue_view(int(h.get("recent", 12))), b""
        if op == "tenants":
            require("fleet:read")
            return {"tenants": hub.tenants()}, b""
        if op == "task":
            require("fleet:submit")
            return {"task": hub.task(int(h["task_id"]))}, b""
        if op == "nodes":
            require("fleet:read")
            return {"nodes": hub.node_table(float(h.get("window_s", 60))), "utilization": hub.utilization(float(h.get("window_s", 60)))}, b""
        if op == "advise":
            require("fleet:read")
            return {"recommendations": hub.advise(float(h.get("window_s", 60)), target_pct=float(h.get("target_pct", 60)))}, b""
        raise ValueError(f"unknown op {op!r}")
    return handle


def serve_hub(token: bytes | None = None, host: str = "127.0.0.1", port: int = 0, allow_remote: bool = False,
              authorizer=None, hub: Hub | None = None, ledger: Ledger | None = None, **server_kw) -> tuple[RpcServer, Hub]:
    hub = hub or Hub(ledger=ledger)
    return RpcServer(make_handler(hub), token, host=host, port=port, allow_remote=allow_remote, authorizer=authorizer, **server_kw), hub


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file")
    ap.add_argument("--master-key-file")
    ap.add_argument("--audit-log")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--allow-remote", action="store_true")
    ap.add_argument("--decision-log", default=str(Path.home() / ".spatial" / "fleet-decisions.jsonl"))
    ap.add_argument("--state-file", help="save tasks, queue, tenant usage here every 5 s and reload it at start")
    ap.add_argument("--peer", action="append", default=[], help="host:port of another hub (repeatable): active/standby with automatic promotion")
    ap.add_argument("--peer-token-file", help="token this hub presents to its peers (scope fleet:replicate); default: --token-file")
    ap.add_argument("--max-finished", type=int, default=5000, help="finished tasks kept in memory (older ones are forgotten)")
    ap.add_argument("--name", default="hub", help="this hub's name (HA tie-break: the smaller name stays active)")
    ap.add_argument("--fail-after", type=float, default=6.0, help="seconds without an active peer before a standby promotes itself")
    a = ap.parse_args()
    if bool(a.token_file) == bool(a.master_key_file):
        raise SystemExit("give exactly one of --token-file or --master-key-file")
    srv, hub = serve_hub(Path(a.token_file).read_bytes() if a.token_file else None, a.host, a.port, a.allow_remote,
                         authorizer_from_file(a.master_key_file, a.audit_log) if a.master_key_file else None,
                         ledger=Ledger(a.decision_log))
    hub.max_finished = a.max_finished
    if a.state_file:
        print("restored", hub.load(a.state_file), flush=True)
    if a.peer:
        from .ha import HAController
        ptf = a.peer_token_file or a.token_file
        if ptf is None:
            raise SystemExit("--peer needs --peer-token-file (a scoped token with fleet:replicate) or --token-file")
        from .ha import QuorumController
        cls = QuorumController if len(a.peer) >= 2 else HAController            # 3 or more hubs: majority election
        kw = {"meta_path": a.state_file + ".term"} if (cls is QuorumController and a.state_file) else {}
        cls(hub, Path(ptf).read_bytes(), a.peer, a.name, fail_after_s=a.fail_after, **kw).start()
    if a.state_file:
        hub.autosave(a.state_file)
    print(f"PORT {srv.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

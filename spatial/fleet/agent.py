"""Fleet agent: measure this machine continuously, report to the hub, run the hub's tasks.

Design points:
  * outbound connections only (the agent never listens);
  * a ring buffer keeps measurements while the hub is unreachable and delivers them, in order,
    on reconnection (each keeps its own timestamp);
  * the agent only runs workloads from the allow-list in compute/workloads.py: it never executes
    code that came from the network.
"""
from __future__ import annotations

import socket
import threading
import time
from collections import deque

from ..compute import workloads
from ..compute.detect import _nvidia_gpus, detect_node
from ..compute.monitor import snapshot
from ..core.protocol import RpcClient
from .ha import connect_active, parse_addrs


class Agent:
    def __init__(self, host: "str | list", port: int | None, token: bytes, name: str | None = None, interval_s: float = 5.0,
                 usd_per_hour: float | None = None, labels: list | None = None, run_tasks: bool = True,
                 poll_s: float = 1.0, buffer: int = 720):
        # one hub, or several (host as a list or "h1:p,h2:p"): the agent talks to whichever reports itself active
        self.hubs = parse_addrs(host) if port is None else [(host, port)]
        self.host, self.port, self.token = self.hubs[0][0], self.hubs[0][1], token
        self.name = name or socket.gethostname()
        self.interval_s, self.poll_s = interval_s, poll_s
        self.usd_per_hour, self.labels, self.run_tasks = usd_per_hour, labels or [], run_tasks
        self._buf: deque = deque(maxlen=buffer)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.sent = self.reconnects = self.tasks_done = 0
        self.last_error: str | None = None
        self._inventory = None

    # ---------------------------------------------------------------- measurement
    def collect(self) -> dict:
        s = snapshot()
        return {"ts": s["ts"], "cpu_percent": s["cpu_percent"], "cpu_count": _cores(), "load1": s["load1"],
                "ram_total": s["ram_total"], "ram_available": s["ram_available"], "swap_used": s["swap_used"],
                "memory_pressure": s.get("memory_pressure"),
                "gpus": [{"name": g["name"], "util": g["utilization_percent"], "vram_total": g["vram_bytes"],
                          "vram_used": g["vram_used_bytes"]} for g in _nvidia_gpus()]}

    # ---------------------------------------------------------------- loops
    def _connect(self) -> RpcClient:
        if len(self.hubs) == 1:
            return RpcClient(self.host, self.port, self.token, timeout=30)
        return connect_active(self.hubs, self.token, timeout=30)

    def _report_loop(self):
        cli = None
        while not self._stop.is_set():
            self._buf.append(self.collect())
            try:
                if cli is None:
                    cli = self._connect()
                    self.reconnects += 1
                while self._buf:
                    m = self._buf[0]
                    extra = {}
                    if self._inventory is None:
                        self._inventory = detect_node().to_dict()
                    if self.sent == 0 or self.reconnects_changed:
                        extra["inventory"] = self._inventory
                    cli.call({"op": "report", "node": self.name, "metrics": m, "usd_per_hour": self.usd_per_hour,
                              "labels": self.labels, **extra})
                    self._buf.popleft()
                    self.sent += 1
                    self.reconnects_changed = False
                self.last_error = None
            except (OSError, ConnectionError, RuntimeError) as e:
                self.last_error = f"{type(e).__name__}: {e}"
                if cli is not None:
                    cli.close()
                cli = None
                self.reconnects_changed = True
            self._stop.wait(self.interval_s)
        if cli is not None:
            cli.close()

    reconnects_changed = True

    def _work_loop(self):
        cli = None
        while not self._stop.is_set():
            try:
                if cli is None:
                    cli = self._connect()
                task = cli.call({"op": "poll", "node": self.name})[0].get("task")
            except (OSError, ConnectionError, RuntimeError):
                if cli is not None:
                    cli.close()
                cli = None
                self._stop.wait(self.poll_s * 2)
                continue
            if not task:
                self._stop.wait(self.poll_s)
                continue
            t0 = time.perf_counter()
            try:
                value = workloads.run(task["workload"], **task["params"])
                msg = {"ok": True, "value": value}
            except Exception as e:
                msg = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            try:
                cli.call({"op": "result", "node": self.name, "task_id": task["id"], "wall_s": time.perf_counter() - t0, **msg})
                self.tasks_done += 1
            except (OSError, ConnectionError, RuntimeError):
                cli = None

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> "Agent":
        self._threads = [threading.Thread(target=self._report_loop, daemon=True)]
        if self.run_tasks:
            self._threads.append(threading.Thread(target=self._work_loop, daemon=True))
        for t in self._threads:
            t.start()
        return self

    def stop(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=10)

    def run_forever(self):
        self.start()
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            self.stop()


def _cores() -> int:
    import psutil
    return psutil.cpu_count(logical=True) or 1

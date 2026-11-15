"""Priority task queue over a local executor slot and N remote workers.

Tasks are allow-listed workloads (name + params), so they are safe to re-run: when a
worker fails mid-task the task is re-queued and the worker is retired. Lower `priority`
runs first; ties keep submission order.
"""
from __future__ import annotations

import heapq
import itertools
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field

from . import workloads


@dataclass(order=True)
class _Item:
    priority: int
    seq: int
    workload: str = field(compare=False)
    params: dict = field(compare=False)
    future: Future = field(compare=False)
    attempts: int = field(compare=False, default=0)


class TaskQueue:
    def __init__(self, workers: dict | None = None, local_slots: int = 1, max_attempts: int = 3):
        """workers: {name: RpcClient}. local_slots: tasks run concurrently in this process."""
        self._heap: list[_Item] = []
        self._cv = threading.Condition()
        self._seq = itertools.count()
        self._closed = False
        self.max_attempts = max_attempts
        self.log: list[dict] = []          # one entry per finished attempt: who ran what, how long
        self.retired: list[str] = []
        self._threads = []
        for i in range(local_slots):
            self._spawn(f"local-{i}", None)
        for name, client in (workers or {}).items():
            self._spawn(name, client)

    def _spawn(self, name, client):
        t = threading.Thread(target=self._loop, args=(name, client), daemon=True)
        t.start()
        self._threads.append(t)

    def submit(self, workload: str, params: dict | None = None, priority: int = 10) -> Future:
        if workload not in workloads.REGISTRY:
            raise KeyError(f"workload '{workload}' is not allow-listed")
        f: Future = Future()
        with self._cv:
            if self._closed:
                raise RuntimeError("queue is closed")
            heapq.heappush(self._heap, _Item(priority, next(self._seq), workload, params or {}, f))
            self._cv.notify()
        return f

    def _loop(self, name, client):
        while True:
            with self._cv:
                while not self._heap and not self._closed:
                    self._cv.wait()
                if not self._heap:
                    return
                item = heapq.heappop(self._heap)
            t0 = time.perf_counter()
            try:
                if client is None:
                    result = workloads.run(item.workload, **item.params)
                else:
                    result = client.call({"op": "run", "workload": item.workload, "params": item.params})[0]["result"]
            except (ConnectionError, OSError) as e:        # executor is gone: give the task back
                item.attempts += 1
                self.log.append({"executor": name, "workload": item.workload, "ok": False, "error": str(e)})
                with self._cv:
                    self.retired.append(name)
                    alive = sum(t.is_alive() for t in self._threads) - 1
                    if item.attempts >= self.max_attempts or alive <= 0:
                        item.future.set_exception(RuntimeError(f"task failed after {item.attempts} attempt(s): {e}"))
                    else:
                        heapq.heappush(self._heap, item)
                        self._cv.notify()
                return                                      # retire this executor
            except Exception as e:                           # the task itself is wrong: do not retry
                self.log.append({"executor": name, "workload": item.workload, "ok": False, "error": str(e)})
                item.future.set_exception(e)
                continue
            self.log.append({"executor": name, "workload": item.workload, "priority": item.priority,
                             "ok": True, "wall_s": time.perf_counter() - t0})
            item.future.set_result(result)

    def close(self, wait: bool = True):
        with self._cv:
            self._closed = True
            self._cv.notify_all()
        if wait:
            for t in self._threads:
                t.join(timeout=60)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

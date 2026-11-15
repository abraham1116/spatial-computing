"""Communicator: point-to-point messages between ranks over SWP/2 (encrypted, authenticated)."""
from __future__ import annotations

import json
import multiprocessing as mp
import queue
import secrets
import threading

import numpy as np

from ..core.protocol import RpcClient, RpcServer

TIMEOUT_S = 120.0


class Comm:
    def __init__(self, rank: int, size: int, token: bytes):
        self.rank, self.size, self.token = rank, size, token
        self._inbox: dict = {}
        self._inbox_lock = threading.Lock()              # two threads must never create two queues for one key
        self._srv = RpcServer(self._handle, token).start()
        self.port = self._srv.port
        self._clients: dict[int, RpcClient] = {}
        self.ports: list[int] = []
        self.bytes_sent = 0

    def _q(self, src: int, tag) -> queue.Queue:
        with self._inbox_lock:
            return self._inbox.setdefault((src, json.dumps(tag)), queue.Queue())

    def _handle(self, h: dict, blob: bytes):
        if h.get("op") == "msg":
            self._q(h["src"], h["tag"]).put(blob)
            return {}, b""
        raise ValueError("unknown op")

    def connect(self, ports: list[int]) -> None:
        self.ports = ports

    def _client(self, dst: int) -> RpcClient:
        if dst not in self._clients:
            self._clients[dst] = RpcClient("127.0.0.1", self.ports[dst], self.token, timeout=TIMEOUT_S)
        return self._clients[dst]

    def send(self, dst: int, tag, arr: np.ndarray) -> None:
        data = np.ascontiguousarray(arr).tobytes()
        self.bytes_sent += len(data)
        self._client(dst).call({"op": "msg", "src": self.rank, "tag": tag}, data)

    def recv(self, src: int, tag, dtype=np.float32) -> np.ndarray:
        try:
            blob = self._q(src, tag).get(timeout=TIMEOUT_S)
        except queue.Empty:
            raise TimeoutError(f"rank {self.rank}: no message from {src} with tag {tag!r}")
        return np.frombuffer(blob, dtype=dtype).copy()

    def barrier(self, tag="barrier") -> None:
        """Dissemination barrier."""
        d, r = 1, 0
        while d < self.size:
            self.send((self.rank + d) % self.size, (tag, r), np.zeros(1, np.float32))
            self.recv((self.rank - d) % self.size, (tag, r))
            d, r = d * 2, r + 1

    def close(self) -> None:
        for c in self._clients.values():
            c.close()
        self._srv.stop()


def _child(rank, size, token, conn, fn, args):
    comm = Comm(rank, size, token)
    conn.send(comm.port)
    comm.connect(conn.recv())
    try:
        conn.send(("ok", fn(comm, *args)))
    except Exception as e:                      # report to the parent instead of dying silently
        conn.send(("error", f"{type(e).__name__}: {e}"))
    finally:
        comm.barrier("exit")
        comm.close()


def launch(size: int, fn, *args, timeout_s: float = 300.0) -> list:
    """Run fn(comm, *args) on `size` ranks, each in its own OS process; returns the results by rank.
    `fn` must be importable (module-level) because processes are spawned."""
    ctx = mp.get_context("spawn")
    token = secrets.token_bytes(32)
    pipes, procs = [], []
    for r in range(size):
        parent, child = ctx.Pipe()
        p = ctx.Process(target=_child, args=(r, size, token, child, fn, args), daemon=True)
        p.start()
        pipes.append(parent)
        procs.append(p)
    ports = [c.recv() for c in pipes]
    for c in pipes:
        c.send(ports)
    out = []
    for r, c in enumerate(pipes):
        if not c.poll(timeout_s):
            for p in procs:
                p.terminate()
            raise TimeoutError(f"rank {r} did not finish in {timeout_s} s")
        status, val = c.recv()
        if status != "ok":
            for p in procs:
                p.terminate()
            raise RuntimeError(f"rank {r}: {val}")
        out.append(val)
    for p in procs:
        p.join(timeout=30)
    return out

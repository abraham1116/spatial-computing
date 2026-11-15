"""TEST — hub failover: two hub PROCESSES (active + standby), one agent; the active hub is killed with SIGKILL.
Measured: time until a hub reports itself active again, and until a task submitted before the kill completes
on the survivor. Default HA settings (poll 1 s, promotion after 6 s of silence). One machine, loopback."""
from __future__ import annotations

import os
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from common import save
from spatial.fleet import Agent
from spatial.fleet.ha import connect_active
from spatial.core.protocol import RpcClient

PY = sys.executable


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def role(port, tok):
    try:
        return RpcClient("127.0.0.1", port, tok, timeout=2).call({"op": "role"})[0]
    except Exception:
        return None


def trial(tmp: Path) -> dict:
    tokf = tmp / "tok"; tokf.write_bytes(b"ha-bench-secret"); tok = tokf.read_bytes()
    pa, pb = free_port(), free_port()
    procs = {}
    for name, port, peer in (("a", pa, pb), ("b", pb, pa)):
        procs[name] = subprocess.Popen([PY, "-m", "spatial.fleet.hub", "--token-file", str(tokf), "--port", str(port), "--name", name,
                                        "--peer", f"127.0.0.1:{peer}", "--decision-log", str(tmp / f"{name}.jsonl")],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    ports = {"a": pa, "b": pb}
    try:
        t0 = time.time()
        while time.time() - t0 < 40 and sum((role(p, tok) or {}).get("role") == "active" for p in ports.values()) != 1:
            time.sleep(0.3)
        startup_s = time.time() - t0
        active = next(n for n, p in ports.items() if (role(p, tok) or {}).get("role") == "active")
        survivor = "b" if active == "a" else "a"
        hubs = f"127.0.0.1:{pa},127.0.0.1:{pb}"
        cli = connect_active(hubs, tok)
        tid = cli.call({"op": "submit", "workload": "montecarlo_pi", "params": {"samples": 1000}})[0]["task_id"]
        cli.close()
        time.sleep(2.5)                                       # the standby copies the queue (poll 1 s)
        agent = Agent(hubs, None, tok, name="n1", interval_s=1.0, poll_s=0.5).start()
        kill_at = time.time()
        procs[active].send_signal(signal.SIGKILL)
        new_active_s = done_s = None
        while time.time() - kill_at < 60:
            r = role(ports[survivor], tok)
            if new_active_s is None and r and r["role"] == "active":
                new_active_s = time.time() - kill_at
            if new_active_s is not None:
                try:
                    c = connect_active(hubs, tok)
                    if c.call({"op": "task", "task_id": tid})[0]["task"]["state"] == "done":
                        done_s = time.time() - kill_at; c.close(); break
                    c.close()
                except Exception:
                    pass
            time.sleep(0.25)
        agent.stop()
        return {"startup_until_one_active_s": startup_s, "kill_to_new_active_s": new_active_s, "kill_to_task_done_s": done_s}
    finally:
        for p in procs.values():
            p.kill()


def main():
    rows = []
    for i in range(3):
        with tempfile.TemporaryDirectory() as d:
            r = trial(Path(d)); rows.append(r)
            print(f"trial {i + 1}: " + ", ".join(f"{k} {v:.1f}" if v is not None else f"{k} FAILED" for k, v in r.items()), flush=True)
    ok = [r for r in rows if r["kill_to_task_done_s"] is not None]
    out = {"trials": rows, "settings": {"poll_s": 1.0, "fail_after_s": 6.0}, "succeeded": len(ok),
           "median_kill_to_new_active_s": statistics.median(r["kill_to_new_active_s"] for r in ok) if ok else None,
           "median_kill_to_task_done_s": statistics.median(r["kill_to_task_done_s"] for r in ok) if ok else None}
    save("ha", out)
    print(out["succeeded"], "of 3 trials completed the task; median kill -> new active", out["median_kill_to_new_active_s"], "s; -> task done", out["median_kill_to_task_done_s"], "s")


if __name__ == "__main__":
    main()

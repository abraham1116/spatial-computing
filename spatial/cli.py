"""`spatial` command line: one entry point for the three operational engines."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHES = {"cpu": "bench_cpu", "memory": "bench_memory", "gpu": "bench_gpu",
           "runtime": "bench_runtime", "q": "bench_q"}


def cmd_audit(a):
    from .compute import detect_node, limitations, snapshot
    from .compute.monitor import underused
    node, snap = detect_node(), snapshot()
    if a.json:
        print(json.dumps({"node": node.to_dict(), "snapshot": snap, "limitations": limitations(node)},
                         indent=1, default=str))
        return 0
    print(f"{node.attrs.get('model')} | {node.attrs.get('cpu_brand')} | {node.os} | {node.arch}")
    for r in node.resources:
        cap = f"{r.capacity / 2**30:.1f} GiB" if r.unit == "bytes" else f"{r.capacity:g} {r.unit}"
        if "utilization_percent" in r.attrs:
            cap += f"  ({r.attrs['utilization_percent']:.0f}% busy)"
        print(f"  {r.kind.value:<11} {r.name:<42} {cap}")
    print(f"memory pressure: {snap.get('memory_pressure')} | compressor ratio: {snap.get('compressor_ratio')} "
          f"| swap used: {snap['swap_used'] / 2**30:.2f} GiB")
    for u in underused(snap):
        print("  idle:", u)
    print("limitations:")
    for x in limitations(node):
        print("  -", x)
    return 0


def cmd_status(a):
    from .core.registry import ENGINES
    for e in ENGINES:
        print(f"{e.name:<42} {e.status.value:<24} not done: {e.not_done}")
    return 0


def cmd_plan(a):
    from .runtime import inspect, plan
    art = inspect(a.file)
    print(f"{a.file}: {art.format} / {art.os} / {','.join(art.arch)} {art.detail}")
    for r in plan(art):
        print(f"  [{'x' if r.feasible else ' '}] {r.name:<16} {r.reason}")
    return 0


def cmd_run(a):
    from .runtime import execute
    e = execute(a.file, a.args, route=a.route, timeout_s=a.timeout)
    if e.stdout:
        print(e.stdout)
    print(f"[spatial] route={e.route} ok={e.ok} wall={e.wall_s:.2f}s "
          + (f"reason: {e.extra.get('not_runnable')}" if not e.ok and e.extra.get("not_runnable") else ""),
          file=sys.stderr)
    return 0 if e.ok else 1


def cmd_q(a):
    from .q import runtime
    sys.argv = ["spatialq", *a.rest]
    runtime.main()
    return 0


def cmd_bench(a):
    names = list(BENCHES) if a.name == "all" else [a.name]
    bdir = ROOT / "benchmarks"
    if not bdir.exists():
        print("benchmarks/ not found: run from a source checkout", file=sys.stderr)
        return 2
    rc = 0
    for n in names:
        rc |= subprocess.run([sys.executable, f"{BENCHES[n]}.py"], cwd=bdir).returncode
    rc |= subprocess.run([sys.executable, "report.py"], cwd=bdir).returncode
    return rc


def cmd_token(a):
    from .core import auth
    if a.action == "init":
        auth.init_master_key(a.master_key_file)
        print(f"master key written to {a.master_key_file} (mode 600). Keep it private; it can issue any credential.")
        return 0
    az = auth.authorizer_from_file(a.master_key_file)
    print(az.issue(a.name, [s for s in a.scopes.split(",") if s], ttl_s=a.ttl, max_ops=a.max_ops, max_bytes=a.max_bytes))
    return 0


def cmd_worker(a):
    mod = {"compute": "spatial.compute.worker", "memory": "spatial.memory.pageserver",
           "runtime": "spatial.runtime.runner"}[a.kind]
    cmd = [sys.executable, "-m", mod, "--host", a.host, "--port", str(a.port)]
    if a.token_file:
        cmd += ["--token-file", a.token_file]
    if a.master_key_file:
        cmd += ["--master-key-file", a.master_key_file]
    if a.audit_log:
        cmd += ["--audit-log", a.audit_log]
    if a.allow_remote:
        cmd.append("--allow-remote")
    return subprocess.run(cmd).returncode


def main(argv=None):
    ap = argparse.ArgumentParser(prog="spatial", description="SPATIAL COMPUTING — measure, decide, prove")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("audit", help="detect hardware, usage and limits of this machine")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_audit)
    sub.add_parser("status", help="honest status of every engine").set_defaults(fn=cmd_status)
    p = sub.add_parser("plan", help="inspect a binary and list execution routes")
    p.add_argument("file")
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("run", help="run a binary through the best feasible route")
    p.add_argument("file")
    p.add_argument("args", nargs="*")
    p.add_argument("--route")
    p.add_argument("--timeout", type=float, default=300)
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("q", help="SPATIAL Q: run|check|qasm|ir <file.sq>")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_q)
    p = sub.add_parser("bench", help="run benchmarks and regenerate docs/RESULTATS.md")
    p.add_argument("name", choices=[*BENCHES, "all"])
    p.set_defaults(fn=cmd_bench)
    p = sub.add_parser("serve", help="start a compute worker, a page server or a sandboxed binary runner (loopback by default)")
    p.add_argument("kind", choices=["compute", "memory", "runtime"])
    p.add_argument("--token-file", help="shared secret: every client may do everything")
    p.add_argument("--master-key-file", help="scoped credentials with quotas and an audit log (see `spatial token`)")
    p.add_argument("--audit-log")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--allow-remote", action="store_true", help="explicit consent to accept LAN connections")
    p.set_defaults(fn=cmd_worker)
    p = sub.add_parser("token", help="scoped credentials: `init` a master key, `issue` a tenant token")
    p.add_argument("action", choices=["init", "issue"])
    p.add_argument("--master-key-file", required=True)
    p.add_argument("--name", default="tenant")
    p.add_argument("--scopes", default="", help="comma list, e.g. run:mandel_numba,mem:read,exec:elf (trailing * = prefix)")
    p.add_argument("--ttl", type=float, default=3600, help="seconds")
    p.add_argument("--max-ops", type=int)
    p.add_argument("--max-bytes", type=int)
    p.set_defaults(fn=cmd_token)
    a = ap.parse_args(argv)
    if getattr(a, "cmd", None) == "serve" and bool(a.token_file) == bool(a.master_key_file):
        ap.error("serve needs exactly one of --token-file or --master-key-file")
    try:
        return a.fn(a)
    except (Exception, SystemExit) as e:  # user-facing tool: one clean line, no traceback
        if isinstance(e, SystemExit) and not isinstance(e.code, str):
            raise
        print(f"spatial: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

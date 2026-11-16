"""`spatial` command line: one entry point for the three operational engines."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
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


def _read_token(path: str) -> bytes:
    raw = Path(path).read_bytes()
    return raw.strip() if raw.startswith(b"spc1.") else raw          # scoped tokens are text, shared secrets are raw bytes


def _hub_client(a):
    from .fleet.ha import connect_active
    return connect_active(a.hub, _read_token(a.token_file), timeout=30)       # a.hub may be "h1:p,h2:p": the active one is used


def cmd_agent(a):
    from .fleet import Agent
    ag = Agent(a.hub, None, _read_token(a.token_file), name=a.name, interval_s=a.interval,
               usd_per_hour=a.usd_per_hour, labels=[x for x in a.labels.split(",") if x], run_tasks=not a.no_tasks)
    print(f"agent '{ag.name}' reporting to {a.hub} every {a.interval:g} s" + ("" if a.no_tasks else "; accepts allow-listed tasks"), flush=True)
    ag.run_forever()
    return 0


def cmd_desktop(a):
    from .runtime.desktop import DesktopError, start
    try:
        d = start(a.app, clipboard=not a.no_clipboard, view_only_link=a.view_link)
    except DesktopError as e:
        print(f"spatial: {e}", file=sys.stderr)
        return 1
    print(f"desktop ({a.app}, {d.runtime}), loopback only: {d.url}", flush=True)
    if d.view_url:
        print(f"view-only link (watch, cannot type or click): {d.view_url}", flush=True)
    print("Ctrl+C removes it", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        d.stop()
    return 0


def cmd_platform(a):
    from .platform import server
    rest = [x for x in a.rest if x != "serve"] if a.rest[:1] == ["serve"] else a.rest
    server.main(rest)
    return 0


def cmd_dashboard(a):
    from .fleet.dashboard import Dashboard
    d = Dashboard(a.hub, _read_token(a.token_file), port=a.port, min_severity=a.min_severity, webhook=a.webhook).start()
    print(f"dashboard (read-only, this machine only): {d.url}", flush=True)
    if a.webhook:
        print(f"alert events are POSTed to {a.webhook}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        d.stop()
    return 0


def cmd_watch(a):
    from .fleet.alerts import AlertEngine, post_webhook
    eng, cli = AlertEngine(a.min_severity), None
    print(f"watching {a.hub} every {a.interval:g} s (alert level: {a.min_severity} and above)", flush=True)
    while True:
        try:
            cli = cli or _hub_client(a)
            events = eng.update(cli.call({"op": "advise", "window_s": a.window})[0]["recommendations"])
        except Exception as e:
            cli = None
            events = [{"event": "hub_unreachable", "key": "hub", "ts": time.time(), "severity": "high", "text": f"{type(e).__name__}: {e}"}] if "hub" not in eng.firing else []
            eng.firing.setdefault("hub", {"since": time.time(), "severity": "high", "text": "hub unreachable"})
        else:
            if "hub" in eng.firing:
                eng.firing.pop("hub"); events.append({"event": "resolved", "key": "hub", "ts": time.time(), "severity": "high", "text": "hub reachable again"})
        for e in events:
            print(f"{time.strftime('%H:%M:%S', time.localtime(e['ts']))} {e['event']:<9} [{e['severity']}] {e['text']}", flush=True)
            if a.webhook:
                try:
                    post_webhook(a.webhook, e)
                except Exception as err:
                    print(f"webhook failed: {err}", flush=True)
        if a.once:
            return 0
        time.sleep(a.interval)


def cmd_fleet(a):
    cli = _hub_client(a)
    if a.action == "status":
        rh, _ = cli.call({"op": "nodes", "window_s": a.window})
        print(f"{'node':<22}{'up':<4}{'cores':>6}{'cpu%':>7}{'ram free%':>10}{'gpus':>5}{'gpu%':>6}{'$/h':>7}  samples")
        f = lambda v, n=0: "-" if v is None else f"{v:.{n}f}"
        for r in rh["nodes"]:
            print(f"{r['node']:<22}{'yes' if r['alive'] else 'NO':<4}{f(r['cores']):>6}{f(r['cpu_avg']):>7}{f(r['ram_avail_pct']):>10}"
                  f"{r['gpu_count']:>5}{f(r['gpu_util_avg']):>6}{f(r['usd_per_hour'], 2):>7}  {r['samples']}")
        u = rh["utilization"]
        print(f"fleet: {u['nodes']} node(s), {u['cores']} cores, CPU utilization "
              f"{'-' if u['cpu_utilization_pct'] is None else format(u['cpu_utilization_pct'], '.1f') + '%'} (last {a.window:g} s)")
    elif a.action == "advise":
        rh, _ = cli.call({"op": "advise", "window_s": a.window})
        if not rh["recommendations"]:
            print("no recommendation: nothing in the measurements justifies a change")
        for r in rh["recommendations"]:
            extra = f"  [estimated saving {r['est_saving_usd_per_hour']:.2f} $/h, {r['est_saving_usd_per_month']:.0f} $/month]" if "est_saving_usd_per_hour" in r else ""
            print(f"[{r['severity']}] {r['kind']}: {r['text']}{extra}")
            print(f"        evidence: {r['evidence']}")
    elif a.action == "submit":
        import json as _json
        rh, _ = cli.call({"op": "submit", "workload": a.workload, "params": _json.loads(a.params),
                          "needs": _json.loads(a.needs)})
        print(rh["task_id"])
    else:
        rh, _ = cli.call({"op": "task", "task_id": a.task_id})
        t = rh["task"]
        print({k: t.get(k) for k in ("id", "state", "node", "result", "error", "wall_s")})
    cli.close()
    return 0


def cmd_optimize(a):
    import json as _json
    from .unified import Job, Objective, Planner, PlanError, Prices
    prices = Prices(local_usd_per_hour=a.local_usd_per_hour, qpu_usd_per_shot=a.qpu_usd_per_shot, qpu_usd_per_task=a.qpu_usd_per_task,
                    ram_usd_gb_hour=a.ram_usd_gb_hour, storage_usd_gb_hour=a.storage_usd_gb_hour)
    obj = Objective(minimize=a.objective, deadline_s=a.deadline, max_ram_bytes=int(a.max_ram_gib * 2**30) if a.max_ram_gib else None,
                    require_isolation=a.isolated, allow_qpu=a.allow_qpu, require_hardware=a.require_hardware)
    hub = _hub_client(a) if a.hub else None
    if a.job == "compute":
        job = Job.compute(a.family, **_json.loads(a.params))
    elif a.job == "binary":
        job = Job.binary(a.file, a.args, a.est_native_s)
    elif a.job == "quantum":
        job = Job.quantum(Path(a.file).read_text(), a.kernel, _json.loads(a.kargs), a.shots)
    elif a.job == "dataset":
        job = Job.dataset(int(a.gib * 2**30), a.accesses, a.locality, a.hot_fraction)
    else:
        job = Job.kv_cache(a.prefix_tokens, a.reuse, a.horizon_h)
    planner = Planner(prices=prices, hub=hub)
    try:
        plan = planner.plan(job, obj)
    except PlanError as e:
        print(e)
        return 1
    print(plan.explain())
    if a.execute:
        ex = planner.execute(plan)
        err = "n/a" if ex.time_error_pct is None else f"{ex.time_error_pct:+.0f}%"
        print(f"\nexecuted {ex.option}: {ex.wall_s:.4g} s (estimated {ex.est_time_s if ex.est_time_s is None else format(ex.est_time_s, '.4g')} s, error {err}); "
              f"cost {ex.actual_cost_usd:.3g} $ (estimated {ex.est_cost_usd if ex.est_cost_usd is None else format(ex.est_cost_usd, '.3g')} $)")
        print("result:", str(ex.result)[:300])
    return 0


def cmd_devices(a):
    from .fabric import discover
    for d in discover():
        print(f"{d.id:<8}{d.kind:<5}{d.vendor:<22}{d.name:<40}{'available' if d.available else 'UNAVAILABLE'}" + (f"  ({d.note})" if d.note else ""))
    return 0


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
           "runtime": "spatial.runtime.runner", "hub": "spatial.fleet.hub"}[a.kind]
    cmd = [sys.executable, "-m", mod, "--host", a.host, "--port", str(a.port)]
    if a.token_file:
        cmd += ["--token-file", a.token_file]
    if a.master_key_file:
        cmd += ["--master-key-file", a.master_key_file]
    if a.audit_log:
        cmd += ["--audit-log", a.audit_log]
    if a.allow_remote:
        cmd.append("--allow-remote")
    cmd += a.extra                       # service-specific flags, e.g. the hub's --state-file, --usage-file, --peer
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
    p.add_argument("kind", choices=["compute", "memory", "runtime", "hub"])
    p.add_argument("--token-file", help="shared secret: every client may do everything")
    p.add_argument("--master-key-file", help="scoped credentials with quotas and an audit log (see `spatial token`)")
    p.add_argument("--audit-log")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--allow-remote", action="store_true", help="explicit consent to accept LAN connections")
    p.set_defaults(fn=cmd_worker)
    p = sub.add_parser("optimize", help="ONE objective for every engine: price each way to do a job, pick the cheapest, optionally run and check")
    p.add_argument("job", choices=["compute", "binary", "quantum", "dataset", "kv"])
    p.add_argument("--family", default="mandel", help="compute: mandel|heat|nbody|hologram|option|ode")
    p.add_argument("--params", default="{}", help="compute: JSON parameters, e.g. '{\"n\":800,\"iters\":300}'")
    p.add_argument("--file", help="binary: path; quantum: .sq file")
    p.add_argument("args", nargs="*", help="binary: arguments")
    p.add_argument("--est-native-s", type=float, default=1.0, help="binary: expected run time when native")
    p.add_argument("--kernel", help="quantum: kernel name"); p.add_argument("--kargs", default="[]"); p.add_argument("--shots", type=int, default=1000)
    p.add_argument("--gib", type=float, default=1.0, help="dataset: size in GiB"); p.add_argument("--accesses", type=int, default=100000)
    p.add_argument("--locality", type=float, default=0.8); p.add_argument("--hot-fraction", type=float, default=0.2)
    p.add_argument("--prefix-tokens", type=int, default=1000); p.add_argument("--reuse", type=float, default=0.5); p.add_argument("--horizon-h", type=float, default=1.0)
    p.add_argument("--objective", choices=["cost", "time"], default="cost")
    p.add_argument("--deadline", type=float); p.add_argument("--max-ram-gib", type=float)
    p.add_argument("--isolated", action="store_true"); p.add_argument("--allow-qpu", action="store_true"); p.add_argument("--require-hardware", action="store_true")
    p.add_argument("--local-usd-per-hour", type=float, default=0.134, help="price of this machine (default is an assumption)")
    p.add_argument("--ram-usd-gb-hour", type=float, default=0.0); p.add_argument("--storage-usd-gb-hour", type=float, default=0.0)
    p.add_argument("--qpu-usd-per-shot", type=float, default=0.0); p.add_argument("--qpu-usd-per-task", type=float, default=0.0)
    p.add_argument("--hub", help="host:port of a fleet hub: nodes become options"); p.add_argument("--token-file")
    p.add_argument("--execute", action="store_true", help="run the chosen option and compare with the estimate")
    p.set_defaults(fn=cmd_optimize)
    sub.add_parser("devices", help="compute devices the planner can use on this machine (CPU, Metal GPU, NVIDIA GPU)").set_defaults(fn=cmd_devices)
    p = sub.add_parser("agent", help="run a fleet agent: measure this machine, report to a hub, run allow-listed tasks")
    p.add_argument("--hub", required=True, help="host:port of the hub")
    p.add_argument("--token-file", required=True, help="shared secret file, or a scoped token with fleet:report,fleet:work")
    p.add_argument("--name")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--usd-per-hour", type=float, help="what this machine costs per hour (for estimates only)")
    p.add_argument("--labels", default="")
    p.add_argument("--no-tasks", action="store_true", help="measure only; never run tasks")
    p.set_defaults(fn=cmd_agent)
    p = sub.add_parser("fleet", help="see and use the fleet through a hub")
    p.add_argument("action", choices=["status", "advise", "submit", "result"])
    p.add_argument("--hub", required=True)
    p.add_argument("--token-file", required=True, help="scoped token with fleet:read (status/advise) or fleet:submit")
    p.add_argument("--window", type=float, default=60.0)
    p.add_argument("--workload"); p.add_argument("--params", default="{}"); p.add_argument("--needs", default="{}")
    p.add_argument("--task-id", type=int)
    p.set_defaults(fn=cmd_fleet)
    p = sub.add_parser("desktop", help="run a graphical Linux app (xterm, xclock, mousepad) in a container and open it in your browser (noVNC, loopback only)")
    p.add_argument("app", nargs="?", default="xterm", choices=["xterm", "xclock", "mousepad"])
    p.add_argument("--no-clipboard", action="store_true", help="no copy and paste between your machine and the desktop")
    p.add_argument("--view-link", action="store_true", help="also print a view-only link for people who only need to watch")
    p.set_defaults(fn=cmd_desktop)
    p = sub.add_parser("platform", help="account service: sign up, sign in, apps, API keys, usage, billing (`spatial platform serve --help`)")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_platform)
    p = sub.add_parser("dashboard", help="read-only fleet dashboard in your browser (served on 127.0.0.1 only, behind a random key)")
    p.add_argument("--hub", required=True, help="host:port, or h1:p,h2:p for a hub pair")
    p.add_argument("--token-file", required=True, help="scoped token with fleet:read")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--min-severity", default="high", choices=["low", "medium", "high"])
    p.add_argument("--webhook", help="POST each alert event (JSON) to this http(s) URL: this sends fleet data off the machine")
    p.set_defaults(fn=cmd_dashboard)
    p = sub.add_parser("watch", help="print alerts as they fire and clear; optional webhook")
    p.add_argument("--hub", required=True); p.add_argument("--token-file", required=True)
    p.add_argument("--interval", type=float, default=10.0); p.add_argument("--window", type=float, default=60.0)
    p.add_argument("--min-severity", default="high", choices=["low", "medium", "high"])
    p.add_argument("--webhook"); p.add_argument("--once", action="store_true")
    p.set_defaults(fn=cmd_watch)
    p = sub.add_parser("token", help="scoped credentials: `init` a master key, `issue` a tenant token")
    p.add_argument("action", choices=["init", "issue"])
    p.add_argument("--master-key-file", required=True)
    p.add_argument("--name", default="tenant")
    p.add_argument("--scopes", default="", help="comma list, e.g. run:mandel_numba,mem:read,exec:elf (trailing * = prefix)")
    p.add_argument("--ttl", type=float, default=3600, help="seconds")
    p.add_argument("--max-ops", type=int)
    p.add_argument("--max-bytes", type=int)
    p.set_defaults(fn=cmd_token)
    a, extra = ap.parse_known_args(argv)
    if getattr(a, "cmd", None) == "serve":
        a.extra = extra                  # forwarded to the service
    elif extra:
        ap.error("unrecognized arguments: " + " ".join(extra))
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

"""Spatial Runtime Engine planner + executor.

plan(artifact, host): ordered list of execution routes, each marked feasible or not WITH the
reason. execute(): runs the first feasible route and returns the app output and timings.
No route is reported as feasible unless its prerequisites were detected on this host.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import microvm
from .inspect import Artifact, inspect


@dataclass
class Route:
    name: str
    feasible: bool
    reason: str
    expected_overhead: str = ""
    isolation: str = ""


@dataclass
class Execution:
    route: str
    ok: bool
    stdout: str
    wall_s: float
    extra: dict = field(default_factory=dict)


def host_caps(node=None) -> dict:
    import platform
    caps = {"os": {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system(), "?"),
            "arch": {"AMD64": "x86_64", "arm64": "aarch64"}.get(platform.machine(), platform.machine()),
            "node": shutil.which("node"), "wine": shutil.which("wine64") or shutil.which("wine"),
            "docker": shutil.which("docker") or shutil.which("podman"),
            "qemu_x86": shutil.which("qemu-system-x86_64"),
            "microvm": all(microvm.available().values())}
    try:
        caps["hvf"] = subprocess.run(["sysctl", "-n", "kern.hv_support"], capture_output=True,
                                     text=True, timeout=5).stdout.strip() == "1"
    except Exception:
        caps["hvf"] = False
    return caps


def plan(art: Artifact, caps: dict | None = None) -> list[Route]:
    caps = caps or host_caps()
    R: list[Route] = []
    same_arch = caps["arch"] in art.arch or ("arm64" in art.arch and caps["arch"] == "aarch64")
    if art.format == "macho":
        ok = caps["os"] == "macos" and same_arch
        R.append(Route("native", ok, "same OS and CPU" if ok else f"host is {caps['os']}/{caps['arch']}, binary is macOS/{art.arch}",
                       "none", "none (host process)"))
    elif art.format == "elf":
        if caps["os"] == "linux" and same_arch:
            R.append(Route("native", True, "same OS and CPU", "none", "none"))
        hv = caps["microvm"] and caps["hvf"] and "x86_64" in art.arch and caps["arch"] == "x86_64"
        R.append(Route("microvm-hvf", hv,
                       "Linux x86_64 guest under Hypervisor.framework" if hv else
                       "needs QEMU + kernel + HVF and an x86_64 guest on an x86_64 host",
                       "VM boot (~1-2 s) + near-native CPU", "hardware VM, no network, no host files"))
        tcg = caps["microvm"] and "x86_64" in art.arch
        R.append(Route("microvm-tcg", tcg,
                       "software emulation (works without HVF or across CPU families)" if tcg else
                       "no kernel/emulator available for this guest architecture",
                       "5-30x slower CPU", "emulated VM"))
        R.append(Route("container", bool(caps["docker"]) and same_arch,
                       "OCI runtime found" if caps["docker"] else "no Docker/Podman installed",
                       "Linux VM shared by containers on macOS", "namespace isolation inside a VM"))
    elif art.format == "pe":
        R.append(Route("native", caps["os"] == "windows" and same_arch,
                       "same OS" if caps["os"] == "windows" else "host is not Windows", "none", "none"))
        R.append(Route("wine", bool(caps["wine"]),
                       "Wine found" if caps["wine"] else
                       "Wine is not installed (not installed automatically: unsigned third-party build, needs user consent)",
                       "API translation, no CPU emulation on x86_64", "host process (weak)"))
        R.append(Route("windows-vm", False,
                       "no Windows image/licence on this machine; would run under QEMU+HVF",
                       "full guest OS (>=4 GB RAM, >=20 GB disk)", "hardware VM"))
        R.append(Route("remote-windows", False, "no remote Windows host configured", "network latency", "remote machine"))
    elif art.format == "wasm":
        ok = bool(caps["node"])
        R.append(Route("wasm-node-wasi", ok, "Node.js WASI runtime found" if ok else "no WASM runtime",
                       "JIT, typically 1.1-2x native", "WASI sandbox (no files/network unless granted)"))
    elif art.format == "script":
        R.append(Route("native-interpreter", True, f"interpreter: {art.detail}", "none", "none"))
    else:
        R.append(Route("none", False, "unrecognised format"))
    return R


_WASI_JS = """
const { WASI } = require('node:wasi'); const fs = require('node:fs');
process.removeAllListeners('warning');
const wasi = new WASI({ version: 'preview1', args: ['app', ...process.argv.slice(3)], env: {} });
(async () => {
  const m = await WebAssembly.compile(fs.readFileSync(process.argv[2]));
  const i = await WebAssembly.instantiate(m, wasi.getImportObject());
  wasi.start(i);
})();
"""


def execute(path: str, args: list[str] | None = None, route: str | None = None, timeout_s: float = 300) -> Execution:
    art = inspect(path)
    routes = plan(art)
    chosen = next((r for r in routes if r.feasible and (route is None or r.name == route)), None)
    if chosen is None:
        why = "; ".join(f"{r.name}: {r.reason}" for r in routes)
        return Execution(route or "none", False, "", 0.0, {"not_runnable": why, "format": art.format})
    args = args or []
    t0 = time.perf_counter()
    if chosen.name in ("native", "native-interpreter"):
        r = subprocess.run([path, *args], capture_output=True, text=True, timeout=timeout_s)
        return Execution(chosen.name, r.returncode == 0, r.stdout.strip(), time.perf_counter() - t0)
    if chosen.name.startswith("microvm-"):
        v = microvm.run_elf(path, args, accel=chosen.name.split("-")[1], timeout_s=timeout_s)
        return Execution(chosen.name, v.ok, v.stdout.strip(), v.total_wall_s,
                         {"boot_s": v.boot_s, "exit_code": v.exit_code, "tail": "" if v.ok else v.raw_tail})
    if chosen.name == "wasm-node-wasi":
        js = Path(os.environ.get("TMPDIR", "/tmp")) / f"spatial-wasi-{os.getpid()}.js"
        js.write_text(_WASI_JS)
        try:
            r = subprocess.run(["node", "--no-warnings", str(js), path, *args], capture_output=True,
                               text=True, timeout=timeout_s)
        finally:
            js.unlink(missing_ok=True)
        return Execution(chosen.name, r.returncode == 0, r.stdout.strip(), time.perf_counter() - t0,
                         {"stderr": r.stderr[-300:]})
    if chosen.name == "wine":
        r = subprocess.run([shutil.which("wine64") or "wine", path, *args], capture_output=True, text=True,
                           timeout=timeout_s)
        return Execution(chosen.name, r.returncode == 0, r.stdout.strip(), time.perf_counter() - t0)
    return Execution(chosen.name, False, "", 0.0, {"not_runnable": "route has no executor yet"})

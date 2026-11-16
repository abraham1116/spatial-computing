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


def find_wine() -> str | None:
    """Wine on PATH, or a user-level unpacked build under ~/.local/share/spatial (no system install)."""
    w = shutil.which("wine64") or shutil.which("wine")
    if w:
        return w
    base = Path.home() / ".local" / "share" / "spatial"
    for cand in sorted(base.glob("**/bin/wine")) if base.exists() else []:
        if os.access(cand, os.X_OK):
            return str(cand)
    return None


def find_oci() -> tuple[str, str, dict] | None:
    """(name, executable, environment) of a container CLI that can reach a running daemon, else None.
    Looks on PATH and in user-level install directories; a Colima socket is used if it exists."""
    home = Path.home()
    want = os.environ.get("SPATIAL_OCI")                 # "docker" or "podman" forces the choice (default: docker first)
    for name in ([want] if want in ("docker", "podman") else ["docker", "podman"]):
        exe = shutil.which(name)
        if not exe:
            for d in (home / ".local" / "bin", home / ".local" / "podman" / "bin"):
                if os.access(d / name, os.X_OK):
                    exe = str(d / name)
                    break
        if not exe:
            continue
        env = dict(os.environ)
        sock = home / ".colima" / "default" / "docker.sock"
        if name == "docker" and "DOCKER_HOST" not in env and sock.exists():
            env["DOCKER_HOST"] = f"unix://{sock}"
        try:
            fmt = "{{.Version.Version}}" if name == "podman" else "{{.ServerVersion}}"
            r = subprocess.run([exe, "info", "--format", fmt], capture_output=True, text=True, timeout=15, env=env)
        except Exception:
            continue
        if r.returncode == 0 and r.stdout.strip():
            return name, exe, env
    return None


def host_caps(node=None) -> dict:
    import platform
    caps = {"os": {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system(), "?"),
            "arch": {"AMD64": "x86_64", "arm64": "aarch64"}.get(platform.machine(), platform.machine()),
            "node": shutil.which("node"), "wine": find_wine(),
            "docker": (find_oci() or (None,))[0],           # only a daemon that answers counts
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
                       f"{caps['docker']} reachable" if caps["docker"] else "no Docker/Podman with a running daemon",
                       "Linux VM shared by containers on macOS", "container: no network, read-only root, no capabilities, 256 MiB, shares the VM kernel"))
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


OCI_IMAGE = "alpine:3.20"


MAX_SHARE_BYTES = 64 * 2 ** 20


def _tar_dir(d: str) -> bytes:
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        t.add(d, arcname=".")
    if buf.tell() > MAX_SHARE_BYTES:
        raise ValueError(f"shared folder is larger than {MAX_SHARE_BYTES // 2**20} MiB")
    return buf.getvalue()


def _untar_into(data: bytes, d: str) -> int:
    """Extract what the container wrote back into `d`, refusing anything that would land outside it."""
    import io
    import tarfile
    n, root = 0, os.path.realpath(d)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r") as t:
        for m in t.getmembers():
            target = os.path.realpath(os.path.join(root, m.name))
            if not (target == root or target.startswith(root + os.sep)) or not (m.isfile() or m.isdir()):
                continue                                           # no links, devices or paths that escape the folder
            if m.size > MAX_SHARE_BYTES:
                continue
            t.extract(m, root, filter="data") if hasattr(tarfile, "data_filter") else t.extract(m, root)
            n += m.isfile()
    return n


def _run_container(path: str, args: list[str], timeout_s: float, t0: float, allow_network: bool = False, share_dir: str | None = None) -> Execution:
    """Run a static Linux ELF in a locked-down container. The file is streamed in through stdin (works with remote
    daemons such as Colima) into a small exec tmpfs; the root filesystem stays read-only. No network, no capabilities,
    non-root user, 256 MiB, 64 processes. Network and a writable shared folder are OFF unless asked for:
    `allow_network`, and `share_dir`, a host folder that is copied into a volume mounted at /work before the run and
    whose changes are copied back afterwards (a copy, not a live mount: it works with remote daemons)."""
    oci = find_oci()
    if oci is None:
        return Execution("container", False, "", 0.0, {"not_runnable": "no container daemon reachable"})
    name, exe, env = oci
    prog = "".join(c for c in os.path.basename(path) if c.isalnum() or c in "._-") or "prog"          # keeps argv[0] meaningful (busybox applets)
    vol, back = None, 0
    mounts: list[str] = []
    try:
        if share_dir:
            d = os.path.realpath(share_dir)
            if not os.path.isdir(d):
                return Execution("container", False, "", 0.0, {"not_runnable": f"share_dir {share_dir} is not a directory"})
            vol = f"spatial-share-{os.getpid()}-{int(time.time() * 1000) % 10**8}"
            subprocess.run([exe, "volume", "create", vol], capture_output=True, check=True, timeout=30, env=env)
            subprocess.run([exe, "run", "--rm", "-i", "--network", "none", "-v", f"{vol}:/work", OCI_IMAGE, "sh", "-c", "cd /work && tar x && chmod -R a+rwX ."],
                           input=_tar_dir(d), capture_output=True, check=True, timeout=120, env=env)
            mounts = ["-v", f"{vol}:/work:rw", "-w", "/work"]
        cmd = [exe, "run", "--rm", "-i", "--network", "bridge" if allow_network else "none", *mounts, "--read-only", "--tmpfs", "/app:rw,exec,nosuid,mode=1777,size=64m",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "256m", "--pids-limit", "64", "--user", "65534:65534",
               OCI_IMAGE, "sh", "-c", f"cat > /app/{prog} && chmod +x /app/{prog} && exec /app/{prog} \"$@\"", "sh", *args]
        try:
            with open(path, "rb") as f:
                run = subprocess.run(cmd, stdin=f, capture_output=True, text=True, timeout=timeout_s, env=env)
        except subprocess.TimeoutExpired:
            return Execution("container", False, "", time.perf_counter() - t0, {"stderr": "timeout", "runtime": name})
        if vol:
            out = subprocess.run([exe, "run", "--rm", "--network", "none", "-v", f"{vol}:/work:ro", OCI_IMAGE, "tar", "c", "-C", "/work", "."],
                                 capture_output=True, timeout=120, env=env)
            if out.returncode == 0:
                back = _untar_into(out.stdout, share_dir)
        return Execution("container", run.returncode == 0, run.stdout.strip(), time.perf_counter() - t0,
                         {"stderr": run.stderr[-300:], "runtime": name, "exit_code": run.returncode, "files_copied_back": back})
    except (subprocess.CalledProcessError, ValueError) as e:
        return Execution("container", False, "", time.perf_counter() - t0, {"stderr": str(getattr(e, "stderr", b"") or e)[-300:], "runtime": name})
    finally:
        if vol:
            subprocess.run([exe, "volume", "rm", "-f", vol], capture_output=True, timeout=30, env=env)


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


def execute(path: str, args: list[str] | None = None, route: str | None = None, timeout_s: float = 300,
            allow_network: bool = False, share_dir: str | None = None) -> Execution:
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
    if chosen.name == "container":
        return _run_container(path, args, timeout_s, t0, allow_network, share_dir)
    if chosen.name == "wine":
        env = {**os.environ, "WINEDEBUG": "-all", "WINEPREFIX": str(Path.home() / ".local/share/spatial/wineprefix")}
        r = subprocess.run([find_wine(), path, *args], capture_output=True, text=True, timeout=timeout_s, env=env)
        return Execution(chosen.name, r.returncode == 0, r.stdout.strip(), time.perf_counter() - t0,
                         {"stderr": r.stderr[-300:]})
    return Execution(chosen.name, False, "", 0.0, {"not_runnable": "route has no executor yet"})

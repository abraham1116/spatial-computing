import shutil
from pathlib import Path

import pytest

from spatial.compute import workloads
from spatial.runtime import execute, inspect, plan
from spatial.runtime import microvm
from spatial.runtime.envs import IsolatedEnv, detect_interpreters
from spatial.runtime.planner import find_wine, host_caps

BUILD = Path(__file__).resolve().parents[1] / "benchmarks" / "build"
needs_build = pytest.mark.skipif(not (BUILD / "bench.wasm").exists(),
                                 reason="run benchmarks/bench_runtime.py first to build the binaries")


@needs_build
@pytest.mark.parametrize("name,fmt,os_", [("bench-macos", "macho", "macos"), ("bench-linux.elf", "elf", "linux"),
                                          ("bench-windows.exe", "pe", "windows"), ("bench.wasm", "wasm", "any")])
def test_inspect_formats(name, fmt, os_):
    a = inspect(str(BUILD / name))
    assert (a.format, a.os) == (fmt, os_)


def test_inspect_script_and_unknown(tmp_path):
    s = tmp_path / "s.sh"
    s.write_text("#!/bin/sh\necho hi\n")
    assert inspect(str(s)).format == "script"
    u = tmp_path / "u.bin"
    u.write_bytes(b"\x00\x01\x02\x03" * 8)
    assert inspect(str(u)).format == "unknown"


@needs_build
def test_native_and_wasm_give_reference_checksum():
    ref = workloads.mandel_python(64, 50)
    for name in ("bench-macos", "bench.wasm"):
        e = execute(str(BUILD / name), ["64", "50"])
        assert e.ok and int(e.stdout.split()[1]) == ref, (name, e)


@needs_build
@pytest.mark.skipif(not all(microvm.available().values()), reason="QEMU/kernel/busybox missing")
def test_linux_elf_runs_in_microvm():
    ref = workloads.mandel_python(64, 50)
    e = execute(str(BUILD / "bench-linux.elf"), ["64", "50"])
    assert e.route == "microvm-hvf" and e.ok, e
    assert int(e.stdout.split()[1]) == ref


@needs_build
@pytest.mark.skipif(find_wine() is not None, reason="Wine present")
def test_windows_exe_is_reported_not_runnable_instead_of_faked():
    e = execute(str(BUILD / "bench-windows.exe"))
    assert not e.ok and "Wine is not installed" in e.extra["not_runnable"]
    assert not any(r.feasible for r in plan(inspect(str(BUILD / "bench-windows.exe"))))


def test_environment_detection_and_isolated_env(tmp_path):
    rts = {r["runtime"]: r for r in detect_interpreters()}
    assert rts["python3"]["present"]
    env = IsolatedEnv(str(tmp_path / "env"))
    env.create()
    r = env.run("import sys; print(sys.prefix)")
    assert r.returncode == 0 and str(tmp_path) in r.stdout     # really a different prefix
    r = env.run("import qiskit")                                # project packages not visible
    assert r.returncode != 0
    env.destroy()


# ---- OCI container route (needs a reachable Docker or Podman daemon; skipped otherwise)
from spatial.runtime.planner import find_oci

_oci = find_oci()
needs_oci = pytest.mark.skipif(_oci is None or not (Path(__file__).resolve().parents[1] / "vendor" / "busybox-x86_64").exists(),
                               reason="no reachable container daemon or no vendor/busybox-x86_64")
BUSYBOX = str(Path(__file__).resolve().parents[1] / "vendor" / "busybox-x86_64")


def test_container_route_is_infeasible_with_a_reason_when_no_daemon_answers():
    caps = {**host_caps(), "docker": None}
    art = inspect(BUSYBOX) if Path(BUSYBOX).exists() else None
    if art is None:
        pytest.skip("no busybox")
    r = next(x for x in plan(art, caps) if x.name == "container")
    assert not r.feasible and "daemon" in r.reason


@needs_oci
def test_a_static_linux_binary_runs_in_a_locked_down_container(tmp_path):
    bb = tmp_path / "busybox"; shutil.copy(BUSYBOX, bb); bb.chmod(0o755)
    BUSYBOX_ = str(bb)
    ex = execute(BUSYBOX_, ["echo", "hello from a container"], route="container", timeout_s=180)
    assert ex.ok and ex.stdout == "hello from a container" and ex.extra["runtime"] == _oci[0]
    # read-only root, no network, no capabilities, non-root: the binary cannot change the system
    w = execute(BUSYBOX_, ["sh", "-c", "touch /pwned 2>&1; echo rc=$?"], route="container", timeout_s=120)
    assert "rc=0" not in w.stdout and ("Read-only" in w.stdout or "denied" in w.stdout)
    n = execute(BUSYBOX_, ["sh", "-c", "wget -q -T 3 -O- http://1.1.1.1 2>&1; echo rc=$?"], route="container", timeout_s=120)
    assert "rc=0" not in n.stdout
    u = execute(BUSYBOX_, ["id", "-u"], route="container", timeout_s=120)
    assert u.stdout == "65534"
    m = execute(BUSYBOX_, ["sh", "-c", "exit 3"], route="container", timeout_s=120)
    assert not m.ok and m.extra["exit_code"] == 3


@needs_oci
def test_container_can_be_given_a_shared_folder_copied_in_and_back_and_network_only_on_request(tmp_path):
    bb = tmp_path / "busybox"; shutil.copy(BUSYBOX, bb); bb.chmod(0o755)
    share = tmp_path / "share"; share.mkdir()
    (share / "in.txt").write_text("hello\n")
    ex = execute(str(bb), ["sh", "-c", "cat /work/in.txt > /work/out.txt; echo from-container >> /work/out.txt"], route="container", timeout_s=180, share_dir=str(share))
    assert ex.ok and (share / "out.txt").read_text() == "hello\nfrom-container\n" and ex.extra["files_copied_back"] >= 2
    assert (share / "in.txt").read_text() == "hello\n"
    # a program cannot write outside the folder it was given, and a link it creates is not followed back to the host
    ev = execute(str(bb), ["sh", "-c", "ln -s /etc/passwd /work/link; echo x > /work/ok.txt"], route="container", timeout_s=120, share_dir=str(share))
    assert ev.ok and not (share / "link").exists() and (share / "ok.txt").exists()
    nonet = execute(str(bb), ["sh", "-c", "wget -q -T 4 -O /dev/null http://example.com; echo rc=$?"], route="container", timeout_s=120)
    assert "rc=0" not in nonet.stdout                                                      # default: no network
    net = execute(str(bb), ["sh", "-c", "wget -q -T 8 -O /dev/null http://example.com; echo rc=$?"], route="container", timeout_s=120, allow_network=True)
    assert "rc=" in net.stdout                                                             # allowed: the call is attempted (success depends on connectivity)
    bad = execute(str(bb), ["true"], route="container", share_dir="/does/not/exist")
    assert not bad.ok and "not a directory" in bad.extra["not_runnable"]


# ---- remote desktop (needs a reachable container daemon; skipped otherwise)
@pytest.mark.skipif(_oci is None, reason="no reachable container daemon")
def test_remote_desktop_serves_a_vnc_session_on_loopback_only_and_refuses_unknown_apps():
    import base64, os, socket, subprocess
    from spatial.runtime.desktop import DesktopError, start
    with pytest.raises(DesktopError):
        start("rm -rf /")                                                              # an allow-list, never a free command
    d = start("xterm", wait_s=120)
    try:
        assert d.url.startswith("http://127.0.0.1:") and len(d.password) >= 12
        s = socket.create_connection(("127.0.0.1", d.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall((f"GET /websockify HTTP/1.1\r\nHost: 127.0.0.1:{d.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                   f"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: binary\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += s.recv(4096)
        head, _, rest = buf.partition(b"\r\n\r\n")
        assert b"101" in head.splitlines()[0]
        while len(rest) < 14:
            rest += s.recv(4096)
        assert rest[2:2 + (rest[1] & 0x7f)].startswith(b"RFB 003.")                      # a real VNC server answers behind the websocket
        s.close()
        out = subprocess.run([d.exe, "port", d.container, "6080/tcp"], capture_output=True, text=True, env=d.env).stdout
        assert out.strip() and all(line.startswith("127.0.0.1:") for line in out.strip().splitlines())      # published on loopback only (the runtime's own report)
    finally:
        d.stop()

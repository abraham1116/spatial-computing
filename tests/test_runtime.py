import shutil
import subprocess
import time
from pathlib import Path

import pytest

from spatial.compute import workloads
from spatial.runtime import execute, inspect, plan
from spatial.runtime import microvm
from spatial.runtime.arch import host_arch
from spatial.runtime.envs import IsolatedEnv, detect_interpreters
from spatial.runtime.inspect import Artifact
from spatial.runtime.planner import find_oci, find_wine, host_caps

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


class _Rfb:
    """A minimal RFB 3.8 client over a websocket (what noVNC does): enough for VNC authentication, key and pointer events."""

    def __init__(self, port):
        import base64, os, socket
        self.s = socket.create_connection(("127.0.0.1", port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /websockify HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: binary\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        self.buf = bytearray(buf.partition(b"\r\n\r\n")[2])

    def _need(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise ConnectionError("closed")
            self.buf.extend(chunk)

    def frame(self):
        import struct
        self._need(2)
        ln, off = self.buf[1] & 0x7f, 2
        if ln == 126:
            self._need(4); ln, off = struct.unpack(">H", bytes(self.buf[2:4]))[0], 4
        self._need(off + ln)
        data = bytes(self.buf[off:off + ln]); del self.buf[:off + ln]
        return data

    def send(self, data):
        import os, struct
        mask = os.urandom(4)
        hdr = bytes([0x82, 0x80 | len(data)]) if len(data) < 126 else bytes([0x82, 0x80 | 126]) + struct.pack(">H", len(data))
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def login(self, password):
        import struct
        try:
            from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
        except ImportError:
            from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
        from cryptography.hazmat.primitives.ciphers import Cipher, modes
        self.frame()                                                                  # "RFB 003.008\n"
        self.send(b"RFB 003.008\n")
        assert self.frame()[0] >= 1
        self.send(bytes([2]))                                                         # VNC authentication
        challenge = self.frame()
        k = bytes(int(f"{b:08b}"[::-1], 2) for b in (password.encode() + b"\0" * 8)[:8])     # VNC reverses the bits of each key byte
        enc = Cipher(TripleDES(k * 3), modes.ECB()).encryptor()                      # DES = 3DES with one key repeated
        self.send(enc.update(challenge[:8]) + enc.update(challenge[8:16]))
        if struct.unpack(">I", self.frame()[:4])[0] != 0:
            self.s.close(); return False
        self.send(bytes([1]))                                                         # ClientInit: shared session
        self.frame()                                                                  # ServerInit
        return True

    def click(self, x, y):
        import struct, time
        for mask in (1, 0):
            self.send(struct.pack(">BBHH", 5, mask, x, y)); time.sleep(0.2)

    def type(self, text):
        import struct, time
        for ch in text + "\n":
            for down in (1, 0):
                self.send(struct.pack(">BBHI", 4, down, 0, 0xff0d if ch == "\n" else ord(ch))); time.sleep(0.02)


@pytest.mark.skipif(_oci is None, reason="no reachable container daemon")
def test_remote_desktop_view_only_password_and_clipboard_policy_are_enforced():
    import subprocess, time
    from spatial.runtime.desktop import start
    d = start("xterm", wait_s=120, clipboard=False, view_only_link=True)
    try:
        assert d.view_url and "view_only=1" in d.view_url and d.view_password != d.password
        run = lambda *a: subprocess.run([d.exe, *a], capture_output=True, text=True, env=d.env).stdout
        args = run("exec", d.container, "ps", "-o", "args")
        assert "-noclipboard" in args and "-nosetclipboard" in args                                             # clipboard off, both ways
        assert not _Rfb(d.port).login("wrong-password")                                                         # a wrong password is refused
        full, view = _Rfb(d.port), _Rfb(d.port)
        assert full.login(d.password) and view.login(d.view_password)                                           # both connect to the same shared session
        deadline = time.time() + 60
        while time.time() < deadline and "xterm" not in run("exec", d.container, "ps", "-o", "args"):                 # the application must be up before anyone types
            time.sleep(0.5)
        time.sleep(3)                                                                                           # and its window mapped (slow runners)
        view.click(300, 200); view.type("touch /tmp/by-viewer"); time.sleep(1.0)                                # the watcher clicks and types...
        listing = run("exec", d.container, "ls", "-a", "/tmp")
        assert ".X11-unix" in listing, "the container stopped answering: " + run("logs", "--tail", "20", d.container)
        assert "by-viewer" not in listing                                                                       # ...and nothing happens
        for attempt in range(6):                                                                                # the owner types (retried: a window may take a moment to take focus)
            full.click(300, 200); full.type("touch /tmp/by-owner")
            end = time.time() + 8
            while time.time() < end and "by-owner" not in run("exec", d.container, "ls", "/tmp"):
                time.sleep(0.5)
            if "by-owner" in run("exec", d.container, "ls", "/tmp"):
                break
        final = run("exec", d.container, "ls", "/tmp")
        assert "by-owner" in final and "by-viewer" not in final, final                                         # the owner's command ran, the watcher's never did
        full.s.close(); view.s.close()
    finally:
        d.stop()


@pytest.mark.skipif(find_oci() is None, reason="no container daemon")
def test_remote_desktop_moves_single_files_both_ways_with_a_size_limit_and_safe_names(tmp_path):
    from spatial.runtime.desktop import Desktop, DesktopError, start
    src = tmp_path / "hello.txt"; src.write_bytes(b"data\x00\xff" * 100)
    d = start("xcalc", wait_s=90)
    try:
        assert d.upload(str(src)).endswith("/transfer/hello.txt")
        out = tmp_path / "back.bin"
        assert d.download("hello.txt", str(out)) == 600 and out.read_bytes() == src.read_bytes()      # binary content survives
        for bad in ("../x", ".hidden", "a b", "x/y"):
            with pytest.raises(DesktopError):
                d.upload(str(src), bad)
        for bad in ("../x", ".hidden", "a b", "", "x/y"):
            with pytest.raises(DesktopError):
                d.download(bad, str(out))
        with pytest.raises(DesktopError):
            d.download("missing.txt", str(out))
        big = tmp_path / "big.bin"; big.write_bytes(b"0" * (Desktop.MAX_TRANSFER + 1))
        with pytest.raises(DesktopError):
            d.upload(str(big))
    finally:
        d.stop()


# ------------------------------------------------------------------------------------------------ ARM64 / cross-arch (robotics, automotive, consoles: mostly ARM edge hardware)
needs_docker = pytest.mark.skipif(find_oci() is None, reason="no reachable container daemon")
_ELF_MACHINE_CODE = {"x86_64": 0x3E, "aarch64": 0xB7}


def _foreign_arch() -> str:
    """An architecture this host is NOT, so the cross-arch branch is exercised rather than the native one."""
    return "x86_64" if host_arch() == "aarch64" else "aarch64"


def _fake_elf(machine_code: int) -> bytes:
    """Just enough of an ELF header for inspect() to report format='elf' and this machine code: no real
    code, so it only exercises the architecture gate, never an actual execution."""
    import struct
    b = bytearray(20)
    b[0:4] = b"\x7fELF"
    b[4], b[5], b[6], b[7] = 2, 1, 1, 0                      # 64-bit, little-endian, version 1, SYSV (-> linux)
    b[16:18] = struct.pack("<H", 2)                          # e_type (unused by inspect())
    b[18:20] = struct.pack("<H", machine_code)               # e_machine
    return bytes(b)


def test_cross_arch_elf_is_refused_without_a_daemon_with_a_clear_reason():
    art = Artifact(path="x", format="elf", os="linux", arch=[_foreign_arch()])
    r = next(x for x in plan(art, {**host_caps(), "docker": None}) if x.name == "container")
    assert not r.feasible and "no Docker/Podman" in r.reason


def test_unrecognised_cross_arch_is_named_not_silently_refused_or_allowed():
    art = Artifact(path="x", format="elf", os="linux", arch=["riscv"])
    r = next(x for x in plan(art, {**host_caps(), "docker": "docker"}) if x.name == "container")   # recognised-arch check comes first: no daemon probe needed
    assert not r.feasible and "unrecognised architecture" in r.reason


def test_cross_arch_reason_never_claims_native_and_distinguishes_emulated_from_same_arch():
    foreign, native = Artifact(path="x", format="elf", os="linux", arch=[_foreign_arch()]), Artifact(path="x", format="elf", os="linux", arch=[host_arch()])
    rf, rn = next(x for x in plan(foreign) if x.name == "container"), next(x for x in plan(native) if x.name == "container")
    assert "emulat" not in rn.reason.lower()                                           # same-arch route never mentions emulation
    assert "same CPU" not in rf.reason and "native" not in rf.reason.lower()            # cross-arch route never claims to be native
    if rf.feasible:
        assert "emulat" in rf.isolation.lower() and "emulat" in rf.expected_overhead.lower()


@needs_docker
def test_cross_arch_route_against_the_real_daemon_is_emulated_or_names_the_missing_handler():
    art = Artifact(path="x", format="elf", os="linux", arch=[_foreign_arch()])
    r = next(x for x in plan(art) if x.name == "container")
    assert r.feasible == ("emulat" in r.reason.lower())
    assert r.feasible or "binfmt_misc handler" in r.reason                             # daemon reachable, arch recognised: must be one or the other


@needs_docker
def test_cross_arch_container_run_passes_the_same_lockdown_flags_as_the_native_route():
    from spatial.runtime import planner as _p
    art = Artifact(path="x", format="elf", os="linux", arch=[_foreign_arch()])
    r = next(x for x in plan(art) if x.name == "container")
    if not r.feasible:
        pytest.skip("no QEMU binfmt_misc handler registered for " + _foreign_arch())
    calls = []
    real_run = subprocess.run
    def spy(cmd, *a, **k):
        calls.append(cmd)
        return real_run(cmd, *a, **k)
    subprocess.run = spy
    try:
        _p._run_container(str(Path(__file__)), [], 30, time.perf_counter(), platform=_p._oci_platform([_foreign_arch()]))
    finally:
        subprocess.run = real_run
    run_cmd = next(c for c in calls if len(c) > 2 and c[1:3] == ["run", "--rm"])
    for flag in ("--read-only", "--cap-drop", "ALL", "--platform", f"linux/{_p._oci_platform([_foreign_arch()])}"):
        assert flag in run_cmd
    assert "--network" in run_cmd and "none" in run_cmd[run_cmd.index("--network") + 1]


# ------------------------------------------------------------------------------------------------ fleet node architecture (runner.py no longer hardcodes x86_64)
def test_runner_refuses_an_elf_of_a_foreign_architecture_and_names_its_own():
    from spatial.runtime.runner import _handler
    foreign = _foreign_arch()
    with pytest.raises(ValueError) as e:
        _handler({"op": "run_elf"}, _fake_elf(_ELF_MACHINE_CODE[foreign]))
    msg = str(e.value)
    assert host_arch() in msg and foreign in msg and "this node's own architecture" in msg


def test_runner_passes_the_arch_gate_for_its_own_architecture(monkeypatch):
    from spatial.runtime import runner as _r
    # stop short of actually booting a micro-VM: the gate under test is the arch check, not execution
    def stub(*a, **k):
        raise RuntimeError("stub: arch gate passed")
    monkeypatch.setattr(_r.microvm, "run_elf", stub)
    with pytest.raises(RuntimeError, match="stub: arch gate passed"):
        _r._handler({"op": "run_elf"}, _fake_elf(_ELF_MACHINE_CODE[host_arch()]))


def test_microvm_is_correctly_unavailable_on_a_non_x86_64_host(monkeypatch):
    """This micro-VM only ever vendored x86_64 (busybox, kernel, qemu-system-x86_64): on any other host
    architecture it must say so, not silently look for an x86_64 emulator it cannot use as a same-arch VM."""
    from spatial.runtime import microvm as _m
    monkeypatch.setattr(_m, "host_arch", lambda: "aarch64")
    avail = _m.available()
    assert not avail["qemu"] and not avail["kernel"] and not avail["busybox"]

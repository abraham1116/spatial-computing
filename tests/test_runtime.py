import shutil
from pathlib import Path

import pytest

from spatial.compute import workloads
from spatial.runtime import execute, inspect, plan
from spatial.runtime import microvm
from spatial.runtime.envs import IsolatedEnv, detect_interpreters
from spatial.runtime.planner import find_wine

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

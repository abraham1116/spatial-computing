"""v0.3: remote sandboxed execution, NVIDIA parsing, cost objective, Wine route."""
from pathlib import Path

import pytest

from spatial.compute import detect_node, workloads
from spatial.compute.detect import parse_nvidia_smi
from spatial.compute.scheduler import ComputeScheduler
from spatial.core.ledger import Ledger
from spatial.runtime import execute, microvm
from spatial.runtime.planner import find_wine
from spatial.runtime.runner import LocalRunnerProcess, run_remote

BUILD = Path(__file__).resolve().parents[1] / "benchmarks" / "build"
vm = pytest.mark.skipif(not all(microvm.available().values()) or not (BUILD / "bench-linux.elf").exists(),
                        reason="micro-VM files or test binaries missing")


@vm
def test_remote_runner_executes_elf_in_sandbox_and_refuses_other_formats():
    ref = workloads.mandel_python(64, 50)
    with LocalRunnerProcess() as r:
        c = r.client()
        out = run_remote(c, str(BUILD / "bench-linux.elf"), ["64", "50"])
        assert out["run_ok"] and int(out["stdout"].split()[1]) == ref and out["accel"] == "hvf"
        with pytest.raises(RuntimeError, match="only accepts Linux"):
            run_remote(c, str(BUILD / "bench-macos"))
        with pytest.raises(RuntimeError, match="metacharacters"):
            run_remote(c, str(BUILD / "bench-linux.elf"), ["1; poweroff"])
        c.close()


def test_nvidia_smi_parser():
    g = parse_nvidia_smi("NVIDIA H100 80GB HBM3, 81559, 40000, 37\nTesla T4, 15360, 0, 0\ngarbage line\n")
    assert [x["name"] for x in g] == ["NVIDIA H100 80GB HBM3", "Tesla T4"]
    assert g[0]["vram_bytes"] == 81559 * 2**20 and g[0]["utilization_percent"] == 37.0
    assert parse_nvidia_smi("") == []


def test_cost_objective_prefers_fewer_cpu_seconds(tmp_path):
    s = ComputeScheduler(detect_node(), Ledger(tmp_path / "l.jsonl"))
    s.warmup()
    rows = s.compare("c", {"n": 200, "iters": 100}, s.mandel_strategies(), skip={"multiprocess_numba"})
    best = s.choose(rows, "cost")
    assert best.cost_usd == min(r.cost_usd for r in rows if r.ok) and best.strategy != "local_python"
    s.close()


@pytest.mark.skipif(find_wine() is None or not (BUILD / "bench-windows.exe").exists(), reason="Wine or test binary missing")
def test_windows_exe_runs_under_wine_with_reference_checksum():
    e = execute(str(BUILD / "bench-windows.exe"), ["64", "50"], timeout_s=240)
    assert e.route == "wine" and e.ok, e
    assert int(e.stdout.split()[1]) == workloads.mandel_python(64, 50)

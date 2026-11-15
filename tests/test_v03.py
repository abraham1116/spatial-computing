"""v0.3: remote sandboxed execution, OpenQASM 2 export, shot cost, NVIDIA parsing, cost objective, Wine route."""
import shutil
from pathlib import Path

import numpy as np
import pytest

from spatial.compute import detect_node, workloads
from spatial.compute.detect import parse_nvidia_smi
from spatial.compute.scheduler import ComputeScheduler
from spatial.core.ledger import Ledger
from spatial.q import compile_kernel, parse, sim
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


def test_qasm2_export_loads_in_qiskit_and_matches():
    qasm2 = pytest.importorskip("qiskit.qasm2")
    from qiskit.quantum_info import Statevector
    src = "quantum k(t) { qubit q[3]; h q[0]; cx q[0], q[1]; p(t) q[1]; cp(t) q[0], q[2]; ry(0.3) q[2]; ccx q[0], q[1], q[2]; } main { }"
    c, _ = compile_kernel(parse(src).kernels["k"], [0.8], opt=False)
    qc = qasm2.loads(c.to_qasm2())
    qc.remove_final_measurements()
    assert np.allclose(np.asarray(Statevector(qc)), sim.run_static(c).vector(), atol=1e-9)
    dyn, _ = compile_kernel(parse("quantum d() { qubit q[1]; let m = measure q[0]; } main { }").kernels["d"], [])
    with pytest.raises(ValueError):
        dyn.to_qasm2()


def test_shot_cost_needs_real_prices():
    c, _ = compile_kernel(parse("quantum k() { qubit q[2]; h q[0]; } main { }").kernels["k"], [])
    with pytest.raises(ValueError, match="no price given"):
        c.shot_cost(1000)
    r = c.shot_cost(1000, usd_per_shot=0.002, usd_per_task=0.3)
    assert r["usd"] == pytest.approx(2.3) and r["usd_per_shot_effective"] == pytest.approx(0.0023)


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

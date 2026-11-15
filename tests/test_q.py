import math
from pathlib import Path

import numpy as np
import pytest

from spatial.q import compile_kernel, parse, run_source
from spatial.q import sim
from spatial.q.backends import BackendUnavailable, get, to_qiskit
from spatial.q.compiler import SQCompileError
from spatial.q.ir import Circuit, Op
from spatial.q.lexer import SQSyntaxError
from spatial.q.runtime import SQRuntimeError

EX = Path(__file__).resolve().parents[1] / "examples"


def _run(src, **kw):
    out = []
    env, rt = run_source(src, out=lambda *a: out.append(a), **kw)
    return env, rt, out


def _tv(a, b, shots):
    keys = set(a) | set(b)
    return 0.5 * sum(abs(a.get(k, 0) - b.get(k, 0)) for k in keys) / shots


# ---------------------------------------------------------------- front end
def test_syntax_errors_carry_line_numbers():
    with pytest.raises(SQSyntaxError, match="line 2"):
        parse("main {\n let x = ;\n}")
    with pytest.raises(SQSyntaxError, match="no main"):
        parse("quantum k() { qubit q[1]; }")
    with pytest.raises(SQSyntaxError, match="acts on 2"):
        parse("quantum k() { qubit q[2]; cx q[0]; } main { }")


def test_semantic_errors():
    p = parse("quantum k(n) { qubit q[n]; h q[5]; } main { }")
    with pytest.raises(SQCompileError, match="out of range"):
        compile_kernel(p.kernels["k"], [2])
    p = parse("quantum k() { qubit q[2]; cx q[0], q[0]; } main { }")
    with pytest.raises(SQCompileError, match="same qubit"):
        compile_kernel(p.kernels["k"], [])
    with pytest.raises(SQRuntimeError, match="must be used with"):
        _run("quantum k() { qubit q[1]; } main { let a = k(); }")


def test_range_and_integer_division_lexing():
    env, _, _ = _run("main { let s = 0; for i in 0..10 { s = s + i; } let h = 10 / 2; let f = 1.5 * 2; }")
    assert env["s"] == 45 and env["h"] == 5 and isinstance(env["h"], int) and env["f"] == 3.0


# ---------------------------------------------------------------- IR + optimiser
def test_optimizer_cancels_and_merges_without_changing_the_state():
    src = """quantum k(a) { qubit q[3];
        h q[0]; h q[0]; x q[1]; cx q[0], q[1]; cx q[0], q[1]; rz(a) q[2]; rz(a) q[2];
        s q[1]; sdg q[1]; ry(0.3) q[0]; cz q[0], q[2]; cz q[2], q[0]; t q[2]; }
        main { }"""
    k = parse(src).kernels["k"]
    raw, _ = compile_kernel(k, [0.4], opt=False)
    opt, info = compile_kernel(k, [0.4], opt=True)
    assert info["ops_before"] == 13 and info["ops_after"] == 4
    assert np.allclose(sim.run_static(raw).vector(), sim.run_static(opt).vector())


def test_optimizer_respects_measurement_barriers():
    k = parse("quantum k() { qubit q[1]; h q[0]; let m = measure q[0]; h q[0]; } main { }").kernels["k"]
    c, _ = compile_kernel(k, [])
    assert [o.name for o in c.ops] == ["h", "measure", "h"]


def test_ir_json_roundtrip_and_resources():
    c = Circuit("c", 3, 1, [Op("h", (0,)), Op("cx", (0, 1)), Op("measure", (0,), cbit=0),
                            Op("x", (2,), cond=((0, 1),)), Op("rz", (1,), (0.25,))])
    c2 = Circuit.from_json(c.to_json())
    assert c2.ops == c.ops
    e = c.estimate()
    assert (e.qubits, e.two_qubit_ops, e.mid_circuit_measurements, e.dynamic) == (3, 1, 1, True)
    assert e.statevector_bytes == 16 * 8


# ---------------------------------------------------------------- simulator vs Qiskit
def test_statevector_matches_qiskit_on_random_circuits():
    from qiskit.quantum_info import Statevector
    rng = np.random.default_rng(5)
    one = ["h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx"]
    rot = ["rx", "ry", "rz", "p"]
    for n in (2, 3, 5):
        ops = []
        for _ in range(60):
            r = rng.random()
            if r < 0.3:
                ops.append(Op(one[rng.integers(len(one))], (int(rng.integers(n)),)))
            elif r < 0.55:
                ops.append(Op(rot[rng.integers(len(rot))], (int(rng.integers(n)),), (float(rng.normal()),)))
            elif r < 0.9 or n < 3:
                a, b = rng.choice(n, 2, replace=False)
                g = ["cx", "cz", "swap", "cp", "crz"][rng.integers(5)]
                ops.append(Op(g, (int(a), int(b)), (float(rng.normal()),) if g in ("cp", "crz") else ()))
            else:
                a, b, c = rng.choice(n, 3, replace=False)
                ops.append(Op("ccx", (int(a), int(b), int(c))))
        circ = Circuit("rand", n, 0, ops)
        mine = sim.run_static(circ).vector()
        ref = np.asarray(Statevector(to_qiskit(circ, measure_all=False)))
        assert abs(np.vdot(ref, mine)) ** 2 == pytest.approx(1.0, abs=1e-9)   # fidelity
        assert np.allclose(mine, ref, atol=1e-9)                               # same global phase too


def test_sampling_matches_aer_including_dynamic_circuits():
    p = parse((EX / "04_teleport.sq").read_text())
    c, _ = compile_kernel(p.kernels["teleport"], [1.0])
    shots = 20000
    mine = get("statevector").sample(c, shots, seed=1)
    aer = get("aer").sample(c, shots, seed=2)
    assert _tv(mine, aer, shots) < 0.03
    p1 = sum(v for k, v in mine.items() if k[0] == "1") / shots       # q[2] is the leftmost bit
    assert p1 == pytest.approx(math.sin(0.5) ** 2, abs=0.02)
    slow = sim.sample(c, 3000, seed=3, dynamic="shots")              # reference path agrees
    assert _tv({k: v * shots // 3000 for k, v in slow.items()}, mine, shots) < 0.06


def test_qasm3_export_is_loadable_by_qiskit_when_importer_present():
    qasm3 = pytest.importorskip("qiskit.qasm3")
    pytest.importorskip("qiskit_qasm3_import")
    from qiskit.quantum_info import Statevector
    p = parse((EX / "05_ghz_qft.sq").read_text())
    c, _ = compile_kernel(p.kernels["ghz"], [4])
    qc = qasm3.loads(c.to_qasm3())
    qc.remove_final_measurements()
    assert np.allclose(np.asarray(Statevector(qc)), sim.run_static(c).vector(), atol=1e-9)


# ---------------------------------------------------------------- whole programs
def test_bell_example():
    env, rt, out = _run((EX / "01_bell.sq").read_text(), seed=3)
    assert set(env["counts"]) == {"00", "11"}
    assert rt.trace[0]["backend"] == "statevector"


def test_vqe_reaches_exact_ground_energy():
    env, rt, _ = _run((EX / "03_vqe_hybrid.sq").read_text())
    Z, X, Y, I = sim.FIXED["z"], sim.FIXED["x"], sim.FIXED["y"], np.eye(2)
    kron = np.kron     # leftmost Pauli acts on the highest qubit, as in the language
    H = (-0.4804 * kron(I, I) + 0.3435 * kron(I, Z) - 0.4347 * kron(Z, I) + 0.5716 * kron(Z, Z)
         + 0.0910 * kron(X, X) + 0.0910 * kron(Y, Y))
    exact = float(np.linalg.eigvalsh(H).min())
    assert env["e"] == pytest.approx(exact, abs=1e-6)
    assert sum(1 for t in rt.trace if t["op"] == "expect") > 100      # really a hybrid loop


def test_expectation_matches_aer():
    p = parse((EX / "03_vqe_hybrid.sq").read_text())
    c, _ = compile_kernel(p.kernels["ansatz"], [0.7])
    for pauli in ("IZ", "ZI", "ZZ", "XX", "YY", "XY"):
        assert get("statevector").expectation(c, pauli) == pytest.approx(get("aer").expectation(c, pauli), abs=1e-9)


def test_classical_distributed_example_uses_worker_when_told():
    from spatial.compute.worker import LocalWorkerProcess
    src = (EX / "02_classical_distributed.sq").read_text().replace("on any", "on worker")
    with LocalWorkerProcess() as w:
        c = w.client()
        env, rt, _ = _run(src, worker_client=c)
        c.close()
    assert env["a"] + env["b"] == env["reference"]
    assert {t["where"] for t in rt.trace if t["op"] == "workload"} == {"cpu", "worker"}


def test_qpu_backend_refuses_instead_of_faking():
    with pytest.raises(BackendUnavailable, match="no QPU provider"):
        _run("quantum k() { qubit q[1]; h q[0]; } main { let c = sample k() shots 10 on qpu; }")


def test_orchestrator_refuses_circuits_that_do_not_fit_in_ram():
    with pytest.raises(SQRuntimeError, match="Not simulable here"):
        _run("quantum big() { qubit q[40]; h q[0]; } main { let c = sample big() shots 1; }")

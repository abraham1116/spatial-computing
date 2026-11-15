"""Commutation-aware peephole rules: they must never change the state, and must find savings."""
import numpy as np
import pytest

from spatial.q import compile_kernel, parse, sim
from spatial.q.ir import Circuit, Op
from spatial.q.compiler import optimize


def _state(c):
    return sim.run_static(c).vector()


@pytest.mark.parametrize("src,after", [
    ("rz(0.3) q[0]; cx q[0], q[1]; rz(0.4) q[0];", 2),                  # rz merges across a CX control
    ("x q[1]; cx q[0], q[1]; x q[1];", 1),                               # x cancels across a CX target
    ("z q[0]; cz q[0], q[1]; z q[0];", 1),                               # z cancels across cz
    ("t q[0]; cp(0.5) q[0], q[1]; tdg q[0];", 1),
    ("rx(0.2) q[1]; cx q[0], q[1]; rx(0.5) q[1]; ccx q[0], q[2], q[1]; rx(-0.7) q[1];", 2),
    ("rz(0.3) q[1]; cx q[0], q[1]; rz(0.4) q[1];", 3),                   # target of CX: must NOT move (no commute)
    ("h q[0]; rz(0.3) q[0]; h q[0]; rz(0.4) q[0];", 4),                  # blocked by h
])
def test_commutation_rules_save_exactly_what_they_should(src, after):
    k = parse(f"quantum k() {{ qubit q[3]; {src} }} main {{ }}").kernels["k"]
    raw, _ = compile_kernel(k, [], opt=False)
    opt, info = compile_kernel(k, [], opt=True)
    assert len(opt.ops) == after, [o.name for o in opt.ops]
    assert np.allclose(_state(raw), _state(opt), atol=1e-12)


def test_fuzz_optimizer_never_changes_the_state_and_often_shrinks():
    rng = np.random.default_rng(11)
    one = ["h", "x", "z", "s", "sdg", "t", "tdg"]
    rot = ["rx", "rz", "p", "ry"]
    saved = 0
    for trial in range(300):
        n = int(rng.integers(2, 5))
        ops = []
        for _ in range(int(rng.integers(8, 40))):
            r = rng.random()
            if r < 0.30:
                ops.append(Op(one[rng.integers(len(one))], (int(rng.integers(n)),)))
            elif r < 0.55:
                ops.append(Op(rot[rng.integers(len(rot))], (int(rng.integers(n)),), (float(rng.choice([0.0, 0.3, -0.3, 1.1])),)))
            elif r < 0.85:
                a, b = rng.choice(n, 2, replace=False)
                g = ["cx", "cz", "cp"][rng.integers(3)]
                ops.append(Op(g, (int(a), int(b)), (0.6,) if g == "cp" else ()))
            elif n >= 3:
                a, b, c = rng.choice(n, 3, replace=False)
                ops.append(Op("ccx", (int(a), int(b), int(c))))
        circ = Circuit("fz", n, 0, ops)
        opt, info = optimize(circ)
        assert np.allclose(_state(circ), _state(opt), atol=1e-9), (trial, [o.name for o in ops])
        assert len(opt.ops) <= len(ops)
        saved += len(ops) - len(opt.ops)
    assert saved > 150


def test_conditional_and_measurement_barriers_are_respected():
    k = parse("quantum k() { qubit q[2]; rz(0.3) q[0]; let m = measure q[1]; if m { x q[0]; } rz(0.4) q[0]; } main { }").kernels["k"]
    c, _ = compile_kernel(k, [])
    assert [o.name for o in c.ops].count("rz") == 2                     # not merged across the conditional x

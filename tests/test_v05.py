"""v0.5: several writers on shared pages, adaptive-profile QIR, compiled classical part."""
import threading
import time
from pathlib import Path

import pytest

from spatial.memory import SharedPages, VersionConflict
from spatial.memory.pageserver import LocalPageServer
from spatial.q import compile_kernel, parse, run_source
from spatial.q.codegen import SQCodegenError, compile_program
from spatial.q.qir import to_qir

EX = Path(__file__).resolve().parents[1] / "examples"


def test_two_writers_never_lose_an_update():
    with LocalPageServer() as ps:
        a, b = SharedPages(ps.client()), SharedPages(ps.client())
        inc = lambda cur: (int(cur or b"0") + 1).to_bytes(8, "big").lstrip(b"\0") or b"\0"
        inc = lambda cur: str(int(cur or b"0") + 1).encode()
        def work(sp):
            for _ in range(150):
                sp.update(7, inc)
        ts = [threading.Thread(target=work, args=(sp,)) for sp in (a, b)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        data, version = a.read(7)
        assert int(data) == 300 and version == 300          # no lost update
        assert a.conflicts + b.conflicts > 0                 # and they really did collide
        with pytest.raises(VersionConflict):
            a.write(7, b"stale", expected_version=1)
        assert a.read(99) == (None, 0)


def test_adaptive_qir_for_dynamic_circuit_verifies():
    p = parse((EX / "04_teleport.sq").read_text())
    c, _ = compile_kernel(p.kernels["teleport"], [1.0])
    ir = to_qir(c)
    assert '"qir_profiles"="adaptive_profile"' in ir and "read_result" in ir and "br i1" in ir
    assert '"required_num_results"="5"' in ir                # 2 mid-circuit + 3 final
    pyqir = pytest.importorskip("pyqir")
    m = pyqir.Module.from_ir(pyqir.Context(), ir)
    assert m.verify() is None
    entry = next(f for f in m.functions if pyqir.is_entry_point(f))
    assert pyqir.required_num_qubits(entry) == 3 and len(entry.basic_blocks) == 5
    neg = parse("quantum k() { qubit q[2]; let m = measure q[0]; if m { x q[1]; } else { h q[1]; } } main { }")
    ir2 = to_qir(compile_kernel(neg.kernels["k"], [])[0])
    assert "xor i1" in ir2 and pyqir.Module.from_ir(pyqir.Context(), ir2).verify() is None


@pytest.mark.parametrize("name", ["01_bell.sq", "03_vqe_hybrid.sq", "04_teleport.sq", "05_ghz_qft.sq", "02_classical_distributed.sq"])
def test_compiled_classical_part_matches_interpreter(name):
    src = (EX / name).read_text()
    out_i, out_c = [], []
    env_i, _ = run_source(src, seed=5, out=lambda *a: out_i.append(a))
    env_c, rt = run_source(src, seed=5, out=lambda *a: out_c.append(a), compiled=True)
    assert env_i == env_c and out_i == out_c
    assert rt.trace                                          # dispatches still traced


def test_compiled_is_faster_on_classical_loops_and_keeps_errors():
    src = "main { let s = 0; for i in 0..200000 { s = s + i % 7 * 2; } let h = 9 / 3; let f = 7 / 2; }"
    t0 = time.perf_counter(); env_i, _ = run_source(src); ti = time.perf_counter() - t0
    t0 = time.perf_counter(); env_c, _ = run_source(src, compiled=True); tc = time.perf_counter() - t0
    assert env_i == env_c and env_c["h"] == 3 and env_c["f"] == 3.5
    assert tc < ti / 3
    with pytest.raises(SQCodegenError, match="undeclared"):
        compile_program(parse("main { x = 1; }"))
    with pytest.raises(SQCodegenError, match="unknown name"):
        compile_program(parse("main { let a = b; }"))
    assert "def t_f(v_n):" in compile_program(parse("task f(n) { return n * 2; } main { let a = f(2); }"))

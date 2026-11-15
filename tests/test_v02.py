"""Tests for the v0.2 additions: encrypted protocol, chained ledger, task queue,
encrypted/replicated far tier, micro-VM input files, SPATIAL Q sub-kernels, noise, QIR."""
import json
import math
import socket
import struct

import numpy as np
import pytest

from spatial.compute.taskqueue import TaskQueue
from spatial.compute.worker import LocalWorkerProcess
from spatial.compute import workloads
from spatial.core.ledger import Ledger
from spatial.core.model import Measurement
from spatial.core.protocol import RpcClient, RpcServer
from spatial.memory import FileBackend, TieredStore
from spatial.memory.secure import EncryptedBackend, PageIntegrityError, ReplicatedBackend
from spatial.q import compile_kernel, parse, run_source, sim
from spatial.q.compiler import SQCompileError
from spatial.q.qir import QirExportError, lower, to_qir
from spatial.runtime import microvm

PAGE = 16384


# ---------------------------------------------------------------- protocol
def test_wire_is_encrypted_and_tampering_is_detected():
    secret = b"TOP-SECRET-PAYLOAD-0123456789"
    seen = bytearray()
    srv = RpcServer(lambda h, b: ({"echo": h["msg"]}, b), b"tok").start()
    # man-in-the-middle relay that records everything and can flip one byte
    relay = socket.socket()
    relay.bind(("127.0.0.1", 0))
    relay.listen(1)
    import threading

    def pump(a, b, flip_at=None):
        n = 0
        try:
            while True:
                d = a.recv(65536)
                if not d:
                    break
                seen.extend(d)
                if flip_at is not None and n <= flip_at < n + len(d):
                    d = bytearray(d)
                    d[flip_at - n] ^= 1
                    d = bytes(d)
                n += len(d)
                b.sendall(d)
        except OSError:
            pass
        finally:
            for s in (a, b):
                try:
                    s.close()
                except OSError:
                    pass

    def serve(flip):
        c, _ = relay.accept()
        up = socket.create_connection(("127.0.0.1", srv.port))
        threading.Thread(target=pump, args=(up, c), daemon=True).start()
        threading.Thread(target=pump, args=(c, up, flip), daemon=True).start()

    try:
        threading.Thread(target=serve, args=(None,), daemon=True).start()
        cl = RpcClient("127.0.0.1", relay.getsockname()[1], b"tok", timeout=5)
        rh, rb = cl.call({"msg": secret.decode()}, secret)
        assert rh["echo"] == secret.decode() and rb == secret
        cl.close()
        assert secret not in bytes(seen)                    # nothing readable on the wire
        threading.Thread(target=serve, args=(100,), daemon=True).start()  # corrupt a byte of the first record
        cl = RpcClient("127.0.0.1", relay.getsockname()[1], b"tok", timeout=5)
        with pytest.raises((ConnectionError, OSError)):
            cl.call({"msg": "x"}, b"y")
    finally:
        relay.close()
        srv.stop()


# ---------------------------------------------------------------- ledger
def test_ledger_chain_detects_edits(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    for i in range(4):
        led.record(Measurement("e", "x", f"s{i}", True, float(i)))
    led.decide("e", "choose s0", "fastest")
    assert led.verify() == (True, None)
    assert Ledger(tmp_path / "l.jsonl").verify() == (True, None)      # reopening continues the chain
    lines = (tmp_path / "l.jsonl").read_text().splitlines()
    row = json.loads(lines[2])
    row["wall_s"] = 0.001                                               # falsify a measurement
    lines[2] = json.dumps(row)
    (tmp_path / "l.jsonl").write_text("\n".join(lines) + "\n")
    assert led.verify() == (False, 2)
    del lines[2]
    (tmp_path / "l.jsonl").write_text("\n".join(lines) + "\n")
    assert led.verify()[0] is False                                     # removal is detected too


# ---------------------------------------------------------------- task queue
def test_queue_priorities_and_distribution():
    with LocalWorkerProcess() as w1, LocalWorkerProcess() as w2:
        c1, c2 = w1.client(), w2.client()
        c1.call({"op": "run", "workload": "mandel_numba", "params": {"n": 8, "iters": 8}})
        c2.call({"op": "run", "workload": "mandel_numba", "params": {"n": 8, "iters": 8}})
        workloads.mandel_numba(8, 8)
        with TaskQueue({"w1": c1, "w2": c2}, local_slots=1) as q:
            futs = [q.submit("mandel_numba", {"n": 300, "iters": 200}) for _ in range(12)]
            ref = workloads.mandel_numba(300, 200)
            assert all(f.result(timeout=120) == ref for f in futs)
        assert {e["executor"] for e in q.log} == {"local-0", "w1", "w2"}
        c1.close()
        c2.close()
    # strict priority order on a single executor
    q = TaskQueue(local_slots=0)
    order = [q.submit("montecarlo_pi", {"samples": 1000, "seed": i}, priority=p) for i, p in enumerate([5, 1, 9, 1])]
    q._spawn("late", None)
    q.close()
    assert [e["priority"] for e in q.log] == [1, 1, 5, 9] and all(f.done() for f in order)
    with pytest.raises(KeyError):
        TaskQueue(local_slots=0).submit("not_allowed")


def test_queue_requeues_when_a_worker_dies():
    w = LocalWorkerProcess()
    c = w.client()
    q = TaskQueue({"w": c}, local_slots=0)
    w.stop()                                                # the only worker is gone before any task runs
    q._spawn("local-late", None)
    f = q.submit("montecarlo_pi", {"samples": 20000, "seed": 1})
    assert f.result(timeout=60) == workloads.montecarlo_pi(20000, 1)
    q.close()


# ---------------------------------------------------------------- far tier security
def test_encrypted_far_tier_hides_content_and_detects_tampering(tmp_path):
    path = tmp_path / "far.bin"
    enc = EncryptedBackend(FileBackend(str(path)))
    st = TieredStore(2 * PAGE, 2 * PAGE, enc, codec_name="none")
    marker = b"CONFIDENTIAL-" * 8
    pages = [marker + bytes([i]) * (PAGE - len(marker)) for i in range(24)]
    for i, p in enumerate(pages):
        st.put(i, p)
    assert marker not in path.read_bytes()                  # ciphertext only at rest
    assert all(st.get(i) == pages[i] for i in range(24))
    # swap two sealed pages: authentication is bound to the page key
    inner = enc.inner
    k1, k2 = list(inner._idx)[:2]
    inner._idx[k1], inner._idx[k2] = inner._idx[k2], inner._idx[k1]
    with pytest.raises(PageIntegrityError):
        enc.get(k1)
    st.close()


def test_replicated_far_tier_survives_a_dead_replica(tmp_path):
    a, b = FileBackend(str(tmp_path / "a")), FileBackend(str(tmp_path / "b"))
    rep = ReplicatedBackend([a, b])
    st = TieredStore(2 * PAGE, 2 * PAGE, rep, codec_name="lz4")
    pages = [np.random.default_rng(i).bytes(PAGE) for i in range(20)]
    for i, p in enumerate(pages):
        st.put(i, p)
    a._idx.clear()                                          # replica A loses everything
    assert all(st.get(i) == pages[i] for i in range(20))
    assert rep.failovers > 0
    with pytest.raises(ValueError):
        ReplicatedBackend([a])
    st.close()


# ---------------------------------------------------------------- micro-VM files
@pytest.mark.skipif(not all(microvm.available().values()), reason="QEMU/kernel/busybox missing")
def test_microvm_sees_only_the_files_it_is_given():
    r = microvm.run_elf(str(microvm.BUSYBOX), ["cat", "/data/hello.txt"], files={"hello.txt": b"from-host-42\n"},
                        app_name="busybox_app", timeout_s=90)
    assert r.ok and r.stdout.strip() == "from-host-42"
    r = microvm.run_elf(str(microvm.BUSYBOX), ["ls", "--color=never", "/data"], files={"a.txt": b"1", "b.txt": b"2"},
                        app_name="busybox_app", timeout_s=90)
    assert r.stdout.split() == ["a.txt", "b.txt"]
    with pytest.raises(ValueError):
        microvm.build_initramfs(b"", [], "/dev/null", files={"../etc/passwd": b"x"})


# ---------------------------------------------------------------- SPATIAL Q
SUB = """
quantum entangle(a: qubit, b: qubit) { h a; cx a, b; }
quantum rot(r: qubit, t: angle) { ry(t) r; }
quantum ghz4() {
    qubit q[4];
    entangle(q[0], q[1]);
    for i in 1..3 { cx q[i], q[i + 1]; }
    rot(q, 0.0);
}
quantum loop(a: qubit) { loop(a); }
quantum bad() { qubit q[1]; loop(q[0]); }
main { let c = sample ghz4() shots 400; }
"""


def test_sub_kernels_inline_on_the_callers_qubits():
    p = parse(SUB)
    c, _ = compile_kernel(p.kernels["ghz4"], [], kernels=p.kernels)
    assert [o.name for o in c.ops][:2] == ["h", "cx"] and c.n_qubits == 4
    env, _ = run_source(SUB, seed=1, out=lambda *a: None)
    assert set(env["c"]) == {"0000", "1111"}
    with pytest.raises(SQCompileError, match="only be called from another kernel"):
        compile_kernel(p.kernels["entangle"], [], kernels=p.kernels)
    with pytest.raises(SQCompileError, match="recursion"):
        compile_kernel(p.kernels["bad"], [], kernels=p.kernels)
    with pytest.raises(SQCompileError, match="unknown kernel"):
        compile_kernel(parse("quantum k() { qubit q[1]; nope(q[0]); } main { }").kernels["k"], [])


def test_depolarising_noise_matches_theory():
    k = parse("quantum k() { qubit q[1]; x q[0]; } main { }").kernels["k"]
    c, _ = compile_kernel(k, [])
    assert sim.sample(c, 500, seed=1) == {"1": 500}
    p, shots = 0.3, 20000
    counts = sim.sample(c, shots, seed=2, noise=p)
    # an X or Y error (2/3 of errors) flips the outcome: P(1) = 1 - 2p/3
    assert counts["1"] / shots == pytest.approx(1 - 2 * p / 3, abs=0.012)
    with pytest.raises(ValueError):
        sim.sample(c, 10, noise=1.5)


def test_qir_lowering_is_exact_up_to_global_phase_and_parses():
    src = """quantum k(t) { qubit q[3]; h q; sx q[0]; p(t) q[1]; cp(t) q[0], q[2]; crz(0.7) q[1], q[2];
             ccx q[0], q[1], q[2]; sdg q[2]; } main { }"""
    c, _ = compile_kernel(parse(src).kernels["k"], [0.9], opt=False)
    a, b = sim.run_static(c).vector(), sim.run_static(lower(c)).vector()
    assert abs(np.vdot(a, b)) ** 2 == pytest.approx(1.0, abs=1e-12)
    ir = to_qir(c)
    assert '"required_num_qubits"="3"' in ir and "__quantum__qis__cnot__body" in ir
    assert struct.unpack(">d", bytes.fromhex(ir.split("double 0x")[1][:16]))[0] == pytest.approx(math.pi / 2)
    pyqir = pytest.importorskip("pyqir")
    m = pyqir.Module.from_ir(pyqir.Context(), ir)
    assert m.verify() is None
    entry = next(f for f in m.functions if pyqir.is_entry_point(f))
    assert pyqir.required_num_qubits(entry) == 3 and pyqir.required_num_results(entry) == 3
    assert '"qir_profiles"="base_profile"' in ir

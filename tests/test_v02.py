"""Tests for the v0.2 additions: encrypted protocol, chained ledger, task queue,
encrypted/replicated far tier, micro-VM input files."""
import json
import socket

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


def test_ledger_chain_survives_concurrent_writers(tmp_path):
    import threading
    led = Ledger(tmp_path / "c.jsonl")

    def work(k):
        for i in range(60):
            led.decide("e", f"t{k}-{i}", "concurrent")

    ts = [threading.Thread(target=work, args=(k,)) for k in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(led.rows()) == 480 and led.verify() == (True, None)

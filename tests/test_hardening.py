"""D5 / G-8: hostile input against the wire protocol and the hub. Pass = no crash,
no hang, the server keeps answering honest clients."""
import os
import random
import socket
import struct
import time

import pytest

from spatial.core.protocol import RpcClient, RpcServer, _mac

TOKEN = b"k" * 32


@pytest.fixture
def srv():
    s = RpcServer(lambda h, b: ({"pong": True, "echo": h.get("x")}, b""), token=TOKEN, handshake_timeout_s=1.0, max_connections=8).start()
    yield s
    s.stop()


def alive(s) -> bool:
    c = RpcClient("127.0.0.1", s.port, TOKEN, timeout=5)
    try:
        return c.call({"op": "ping"})[0]["pong"]
    finally:
        c.close()


def test_silent_peers_are_dropped_after_the_handshake_timeout_and_slots_are_freed(srv):
    socks = [socket.create_connection(("127.0.0.1", srv.port)) for _ in range(8)]      # fills every slot, sends nothing
    time.sleep(0.3)
    with pytest.raises(Exception):                                                      # a 9th honest client is refused while full
        alive(srv)
    time.sleep(1.5)                                                                     # handshake timeout frees them
    assert alive(srv)
    for x in socks:
        x.close()


def test_connections_over_the_cap_are_dropped_not_queued_forever(srv):
    held = [RpcClient("127.0.0.1", srv.port, TOKEN) for _ in range(8)]
    with pytest.raises(Exception):
        RpcClient("127.0.0.1", srv.port, TOKEN, timeout=2).call({"op": "ping"})
    for c in held:
        c.close()
    time.sleep(0.3)
    assert alive(srv)


def test_replayed_handshake_is_rejected(srv):
    # record a valid client handshake against one server nonce, replay it on a new connection
    a = socket.create_connection(("127.0.0.1", srv.port))
    hello = a.recv(48, socket.MSG_WAITALL)
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from spatial.core.protocol import _RAW
    eph = X25519PrivateKey.generate()
    pub_c, nonce_c = eph.public_key().public_bytes(**_RAW), os.urandom(16)
    blob = struct.pack(">H", 0) + pub_c + nonce_c + _mac(TOKEN, hello[:16], hello[16:], pub_c, nonce_c, b"")
    a.close()
    b = socket.create_connection(("127.0.0.1", srv.port))
    b.recv(48, socket.MSG_WAITALL)
    b.sendall(blob)                                                                     # new server nonce: the MAC cannot match
    b.settimeout(3)
    assert b.recv(1) == b""                                                             # silent drop
    b.close()
    assert alive(srv)


def test_random_garbage_before_and_after_the_handshake_never_hurts_the_server(srv):
    rng = random.Random(5)
    for _ in range(60):
        s = socket.create_connection(("127.0.0.1", srv.port))
        try:
            s.sendall(bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 200))))
            s.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        s.close()
    assert alive(srv)


def test_tampered_records_and_malformed_plaintext_from_an_authenticated_peer(srv):
    c = RpcClient("127.0.0.1", srv.port, TOKEN)
    ch = c._ch
    ct = bytearray(ch._tx.encrypt(b"\0\0\0\0" + struct.pack(">Q", ch._ntx), b"x" * 40, None))
    ct[5] ^= 1                                                                          # flip a bit
    c.sock.sendall(struct.pack(">I", len(ct)) + bytes(ct))
    c.sock.settimeout(3)
    assert c.sock.recv(1) == b""                                                        # connection dropped
    # authenticated and well-encrypted but structurally wrong plaintexts
    for plain in (b"", b"abc", struct.pack(">II", 5, 5) + b"zz", struct.pack(">II", 2, 0) + b"[]", struct.pack(">II", 3, 0) + b"\xff\xfe\xfd"):
        c2 = RpcClient("127.0.0.1", srv.port, TOKEN)
        e = c2._ch._tx.encrypt(b"\0\0\0\0" + struct.pack(">Q", 0), plain, None)
        c2.sock.sendall(struct.pack(">I", len(e)) + e)
        c2.sock.settimeout(3)
        assert c2.sock.recv(1) == b""
        c2.sock.close()
    assert alive(srv)


def test_oversized_declared_frame_is_refused_without_allocating_it(srv):
    c = RpcClient("127.0.0.1", srv.port, TOKEN)
    c.sock.sendall(struct.pack(">I", 2 ** 31))
    c.sock.settimeout(3)
    assert c.sock.recv(1) == b""
    assert alive(srv)


def test_hub_survives_random_requests_from_an_authenticated_client():
    from spatial.fleet import Hub
    from spatial.fleet.hub import make_handler
    rng = random.Random(9)
    hub = Hub()
    h = make_handler(hub)
    ops = ["ping", "report", "poll", "result", "submit", "submit_gang", "task", "nodes", "advise", "tenants", "nope", None, 5]
    vals = [None, 0, -1, 2 ** 70, "x", "", [], {}, [1, 2], {"a": 1}, 1.5, float("nan"), "n" * 200, True]
    bad = 0
    for _ in range(1500):
        hd = {"op": rng.choice(ops)}
        for k in rng.sample(["node", "metrics", "workload", "params", "params_list", "needs", "task_id", "ok", "window_s", "priority", "tenant"], rng.randrange(0, 5)):
            hd[k] = rng.choice(vals)
        try:
            h(hd, b"")
        except Exception:
            bad += 1                                                                   # the server turns these into {"ok": false}
    assert bad > 0 and isinstance(hub.tenants(), list)                                  # raised cleanly, state still readable


def test_a_burst_of_simultaneous_connections_all_succeed():
    import threading
    s = RpcServer(lambda h, b: ({"pong": True}, b""), token=TOKEN).start()
    fails = []

    def go():
        try:
            c = RpcClient("127.0.0.1", s.port, TOKEN, timeout=30); c.call({"op": "ping"}); c.close()
        except Exception as e:
            fails.append(repr(e))
    ths = [threading.Thread(target=go) for _ in range(100)]
    [t.start() for t in ths]; [t.join() for t in ths]
    s.stop()
    assert not fails, fails[:3]                      # with the old listen backlog of 5, many of these were refused

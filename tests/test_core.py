import socket

import pytest

from spatial.core.ledger import Ledger
from spatial.core.model import Measurement
from spatial.core.protocol import RpcClient, RpcServer
from spatial.core.registry import ENGINES, Status


def _echo(h, b):
    if h.get("op") == "boom":
        raise ValueError("boom")
    return {"echo": h}, b[::-1]


def test_rpc_roundtrip_and_error_reporting():
    srv = RpcServer(_echo, b"secret").start()
    try:
        c = RpcClient("127.0.0.1", srv.port, b"secret")
        rh, rb = c.call({"op": "x", "n": 1}, b"abc")
        assert rh["echo"]["n"] == 1 and rb == b"cba"
        with pytest.raises(RuntimeError, match="boom"):
            c.call({"op": "boom"})
        rh, _ = c.call({"op": "still-alive"})     # server survives handler errors
        assert rh["ok"]
        c.close()
    finally:
        srv.stop()


def test_rpc_rejects_bad_token():
    srv = RpcServer(_echo, b"secret").start()
    try:
        c = RpcClient("127.0.0.1", srv.port, b"wrong", timeout=3)
        with pytest.raises((ConnectionError, OSError, socket.timeout)):
            c.call({"op": "x"})
    finally:
        srv.stop()


def test_server_refuses_public_bind_without_consent():
    with pytest.raises(PermissionError):
        RpcServer(_echo, b"t", host="0.0.0.0")


def test_ledger_roundtrip(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    led.record(Measurement("e", "x", "s", True, 1.0))
    led.decide("e", "choose s", "fastest")
    assert len(led.rows("measurement")) == 1 and len(led.rows("decision")) == 1


def test_registry_never_overclaims():
    assert all(e.evidence and e.not_done for e in ENGINES)
    assert all(e.status in set(Status) for e in ENGINES)

"""Forward secrecy, scoped permissions, quotas and audit trail (SWP/2)."""
import socket
import threading
import time

import pytest

from spatial.compute import workloads
from spatial.compute.worker import serve as serve_worker
from spatial.core import auth
from spatial.core.ledger import Ledger
from spatial.core.protocol import RpcClient, RpcServer
from spatial.memory.pageserver import PageStore


def _echo(h, b):
    return {"echo": h.get("v")}, b


def test_session_keys_are_ephemeral_so_a_leaked_secret_cannot_decrypt_a_recording():
    """Record a session, then hand the attacker the long-term secret: still unreadable."""
    secret = b"long-term-secret-0123456789"
    srv = RpcServer(_echo, secret).start()
    rec = {"c2s": bytearray(), "s2c": bytearray()}
    relay = socket.socket()
    relay.bind(("127.0.0.1", 0))
    relay.listen(1)

    def pump(a, b, key):
        try:
            while d := a.recv(65536):
                rec[key].extend(d)
                b.sendall(d)
        except OSError:
            pass

    def accept():
        c, _ = relay.accept()
        up = socket.create_connection(("127.0.0.1", srv.port))
        threading.Thread(target=pump, args=(up, c, "s2c"), daemon=True).start()
        threading.Thread(target=pump, args=(c, up, "c2s"), daemon=True).start()

    threading.Thread(target=accept, daemon=True).start()
    cl = RpcClient("127.0.0.1", relay.getsockname()[1], secret, timeout=5)
    cl.call({"v": "classified"}, b"payload-bytes")
    cl.close()
    time.sleep(0.2)
    s2c, c2s = bytes(rec["s2c"]), bytes(rec["c2s"])
    nonce_s, pub_s = s2c[:16], s2c[16:48]
    cl_len = int.from_bytes(c2s[:2], "big")
    pub_c, nonce_c = c2s[2 + cl_len:2 + cl_len + 32], c2s[2 + cl_len + 32:2 + cl_len + 48]
    # the attacker knows the secret and saw both public keys and both nonces; without an
    # ephemeral private key the best it can do is the old, secret-only derivation:
    from cryptography.exceptions import InvalidTag
    from spatial.core.protocol import SecureChannel
    forged = SecureChannel(socket.socket(), secret, nonce_s, nonce_c, is_server=False)
    record = s2c[48:]
    n = int.from_bytes(record[:4], "big")
    with pytest.raises(InvalidTag):
        forged._rx.decrypt(b"\0\0\0\0" + (0).to_bytes(8, "big"), record[4:4 + n], None)
    assert b"classified" not in bytes(rec["c2s"]) + bytes(rec["s2c"])
    relay.close()
    srv.stop()


def test_two_sessions_never_share_keys():
    srv = RpcServer(_echo, b"tok").start()
    hellos = []
    for _ in range(2):
        s = socket.create_connection(("127.0.0.1", srv.port))
        hellos.append(s.recv(48))
        s.close()
    assert hellos[0] != hellos[1] and hellos[0][16:] != hellos[1][16:]       # fresh nonce and ephemeral key each time
    srv.stop()


def test_scoped_credentials_enforce_scopes_quotas_expiry_revocation_and_audit(tmp_path):
    az = auth.Authorizer(b"m" * 32, Ledger(tmp_path / "audit.jsonl"))
    srv = serve_worker(None, authorizer=az).start()
    port = srv.port
    alice = az.issue("alice", ["run:montecarlo_pi"], ttl_s=60, max_ops=3)
    root = az.issue("root", ["*"], ttl_s=60)
    short = az.issue("shorty", ["*"], ttl_s=0.3)
    c = RpcClient("127.0.0.1", port, alice.encode(), timeout=10)
    ok, _ = c.call({"op": "run", "workload": "montecarlo_pi", "params": {"samples": 1000, "seed": 1}})
    assert ok["result"] == workloads.montecarlo_pi(1000, 1)
    with pytest.raises(RuntimeError, match="PermissionError.*run:mandel_numba"):      # scope not granted
        c.call({"op": "run", "workload": "mandel_numba", "params": {"n": 8, "iters": 8}})
    c.call({"op": "ping"})                                                           # 3rd op: quota reached
    with pytest.raises(RuntimeError, match="QuotaExceeded"):
        c.call({"op": "ping"})
    c.close()
    r = RpcClient("127.0.0.1", port, root.encode(), timeout=10)
    assert r.call({"op": "run", "workload": "mandel_numba", "params": {"n": 8, "iters": 8}})[0]["ok"]
    r.close()
    time.sleep(0.5)
    with pytest.raises((ConnectionError, OSError)):                                  # expired: silently dropped
        RpcClient("127.0.0.1", port, short.encode(), timeout=3).call({"op": "ping"})
    az.revoke("root")
    with pytest.raises((ConnectionError, OSError)):
        RpcClient("127.0.0.1", port, root.encode(), timeout=3).call({"op": "ping"})
    cred, sec = alice.split("~")
    i = len(auth.PREFIX) + 4                                                          # inside the signed payload
    forged = cred[:i] + ("A" if cred[i] != "A" else "B") + cred[i + 1:] + "~" + sec
    with pytest.raises((ConnectionError, OSError)):                                  # altered credential
        RpcClient("127.0.0.1", port, forged.encode(), timeout=3).call({"op": "ping"})
    with pytest.raises((ConnectionError, OSError)):                                  # wrong master / plain token
        RpcClient("127.0.0.1", port, b"just-a-token", timeout=3).call({"op": "ping"})
    srv.stop()
    rows = [r for r in Ledger(tmp_path / "audit.jsonl").rows("decision") if r["engine"] == "auth"]
    assert any(r["decision"] == "alice:run" and r["reason"].startswith("denied") for r in rows)
    assert any(r["decision"] == "alice:ping" and r["reason"].startswith("denied: QuotaExceeded") for r in rows)
    assert any(r["decision"] == "root:run" and r["reason"] == "allowed" for r in rows)
    assert Ledger(tmp_path / "audit.jsonl").verify() == (True, None)                 # audit trail is tamper-evident


def test_memory_scopes_split_read_from_write_and_byte_quota():
    az = auth.Authorizer(b"k" * 32)
    store = PageStore()
    srv = RpcServer(store.handle, authorizer=az).start()
    reader = RpcClient("127.0.0.1", srv.port, az.issue("r", ["mem:read"]).encode(), timeout=10)
    writer = RpcClient("127.0.0.1", srv.port, az.issue("w", ["mem:*"], max_bytes=100).encode(), timeout=10)
    writer.call({"op": "put", "key": 1}, b"x" * 60)
    assert reader.call({"op": "get", "key": 1})[1] == b"x" * 60
    with pytest.raises(RuntimeError, match="mem:write"):
        reader.call({"op": "put", "key": 2}, b"nope")
    with pytest.raises(RuntimeError, match="QuotaExceeded"):
        writer.call({"op": "put", "key": 3}, b"y" * 60)                               # 60 + 60 > 100
    assert 2 not in store.pages and 3 not in store.pages
    srv.stop()


def test_master_key_handling(tmp_path):
    p = tmp_path / "master.key"
    auth.init_master_key(p)
    assert oct(p.stat().st_mode & 0o777) == "0o600" and len(p.read_bytes()) == 32
    with pytest.raises(FileExistsError):
        auth.init_master_key(p)
    with pytest.raises(ValueError):
        auth.Authorizer(b"short")
    with pytest.raises(ValueError):
        RpcServer(_echo)

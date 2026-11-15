"""Fleet dashboard and alerts: read-only, loopback, keyed, edge-triggered alerts, webhook."""
import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from spatial.fleet import Hub, serve_hub
from spatial.fleet.alerts import AlertEngine, post_webhook
from spatial.fleet.dashboard import Dashboard

TOK = b"dash"
GB = 2 ** 30


class Clock:
    t = 1_000_000.0
    def __call__(self): return self.t


def feed(hub, name, cpu, clk, n=5):
    for i in range(n):
        hub.report(name, {"ts": clk.t - (n - 1 - i) * 5, "cpu_percent": cpu, "cpu_count": 4, "load1": 1.0, "ram_total": 16 * GB,
                          "ram_available": 8 * GB, "swap_used": 0, "memory_pressure": "normal", "gpus": []}, usd_per_hour=1.0)


def get(port, path, host=None, method="GET"):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.putrequest(method, path, skip_host=host is not None)
    if host is not None:
        c.putheader("Host", host)
    c.endheaders()
    r = c.getresponse()
    return r.status, r.read()


def test_alert_engine_fires_once_and_resolves_once_and_filters_by_severity():
    t = [0.0]
    eng = AlertEngine("high", clock=lambda: t[0])
    down = {"kind": "node_down", "severity": "high", "node": "n1", "text": "n1 is down"}
    med = {"kind": "rebalance", "severity": "medium", "node": "n2", "text": "move work"}
    assert [e["event"] for e in eng.update([down, med])] == ["firing"]          # medium is below the level
    assert eng.update([down, med]) == []                                         # still firing: no repeat
    t[0] = 30
    ev = eng.update([med])
    assert [e["event"] for e in ev] == ["resolved"] and ev[0]["lasted_s"] == 30
    assert eng.firing == {} and len(eng.history) == 2
    with pytest.raises(ValueError):
        AlertEngine("urgent")


def test_dashboard_serves_state_only_on_loopback_with_the_key_and_read_only():
    clk = Clock(); hub = Hub(clock=clk)
    feed(hub, "n1", 30, clk); feed(hub, "<img src=x onerror=alert(1)>", 40, clk)
    hub.submit("montecarlo_pi", {"samples": 1}, tenant="T")
    srv, _ = serve_hub(TOK, hub=hub); srv.start()
    d = Dashboard(f"127.0.0.1:{srv.port}", TOK, port=0, interval_s=0.2).start()
    try:
        d.refresh()
        assert d._http.server_address[0] == "127.0.0.1"
        assert get(d.port, "/")[0] == 403                                        # no key
        assert get(d.port, "/?key=wrong")[0] == 403
        assert get(d.port, f"/?key={d.key}", host="evil.example.com")[0] == 403  # DNS rebinding
        assert get(d.port, f"/?key={d.key}", method="POST")[0] == 405            # read-only
        st, page = get(d.port, f"/?key={d.key}")
        assert st == 200 and b"Spatial Fleet" in page and b"esc=" in page       # page escapes what it prints
        st, body = get(d.port, f"/api/state?key={d.key}")
        s = json.loads(body)
        assert st == 200 and {n["node"] for n in s["nodes"]} == {"n1", "<img src=x onerror=alert(1)>"}
        assert s["queue"]["counts"] == {"queued": 1} and s["tenants"][0]["tenant"] == "T" and s["hub"]["role"] == "active"
        assert get(d.port, f"/other?key={d.key}")[0] == 404
    finally:
        d.stop(); srv.stop()


def test_node_down_alert_reaches_the_webhook_and_the_dashboard_state():
    clk = Clock(); hub = Hub(clock=clk, stale_after_s=30)
    feed(hub, "n1", 30, clk)
    srv, _ = serve_hub(TOK, hub=hub); srv.start()
    got = []

    class W(BaseHTTPRequestHandler):
        def do_POST(self):
            got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200); self.end_headers()
        def log_message(self, *a): pass
    web = HTTPServer(("127.0.0.1", 0), W)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    d = Dashboard(f"127.0.0.1:{srv.port}", TOK, interval_s=60, webhook=f"http://127.0.0.1:{web.server_address[1]}/hook")
    try:
        d.refresh()
        assert d.state["alerts"]["firing"] == {} and got == []
        clk.t += 120                                                             # n1 stops reporting
        d.refresh()
        assert any(k.startswith("node_down") for k in d.state["alerts"]["firing"])
        assert [e["event"] for e in got] == ["firing"] and "n1" in got[0]["text"]
        d.refresh()
        assert len(got) == 1                                                     # edge-triggered: no repeat
        feed(hub, "n1", 30, clk)
        d.refresh()
        assert [e["event"] for e in got] == ["firing", "resolved"]
    finally:
        srv.stop(); web.shutdown()
    with pytest.raises(ValueError):
        post_webhook("file:///etc/passwd", {})


def test_dashboard_keeps_serving_and_reports_the_error_when_the_hub_is_down():
    d = Dashboard("127.0.0.1:1", TOK, port=0)
    s = d.refresh()
    assert "error" in s

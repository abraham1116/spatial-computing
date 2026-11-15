"""Fleet dashboard: a local, read-only web page over the hub.

The process holds the hub credential and serves HTTP on 127.0.0.1 ONLY (no option to bind elsewhere).
Every request needs a random key printed at start; the Host header must be loopback (blocks DNS
rebinding); only GET is accepted; the page can read the fleet and cannot change anything.
"""
from __future__ import annotations

import http.server
import json
import secrets
import threading
import time
from urllib.parse import parse_qs, urlparse

from .alerts import AlertEngine, post_webhook
from .ha import connect_active

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spatial Fleet</title><style>
:root{--paper:#f6f4ec;--ink:#12233f;--mute:#4f5f7a;--mark:#ffd84a;--ok:#2f8f3a;--bad:#c0392b;--warn:#b7791f;--grid:#12233f14;
--serif:"Instrument Serif",Georgia,serif;--mono:"DM Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root{--paper:#0e1a30;--ink:#f6f4ec;--mute:#9fb0cc;--grid:#f6f4ec14;--ok:#b8f171;--bad:#ff8a7a;--warn:#ffd84a}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.5 var(--mono);
background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);background-size:24px 24px}
header{display:flex;justify-content:space-between;align-items:baseline;padding:18px 24px;border-bottom:1px solid var(--ink);background:var(--paper)}
h1{font:400 32px var(--serif);margin:0}h2{font:400 22px var(--serif);margin:0 0 8px}
main{max-width:1180px;margin:0 auto;padding:16px 24px;display:grid;gap:16px}
section{background:var(--paper);border:1px solid var(--ink);padding:14px 16px;overflow-x:auto}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:4px 10px 4px 0;white-space:nowrap}th{color:var(--mute);font-weight:400}
.bar{display:inline-block;width:90px;height:8px;border:1px solid var(--ink);vertical-align:middle;margin-right:6px}.bar i{display:block;height:100%;background:var(--ink)}
.tag{padding:1px 6px;border:1px solid currentColor}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}.mute{color:var(--mute)}
#banner{display:none;background:var(--bad);color:#fff;padding:10px 24px}
.kpis{display:flex;gap:28px;flex-wrap:wrap}.kpis b{font:400 30px var(--serif);display:block}
</style></head><body>
<div id="banner" role="alert"></div>
<header><h1>Spatial Fleet</h1><span id="meta" class="mute">connecting…</span></header>
<main>
<section><div class="kpis" id="kpis"></div></section>
<section><h2>Alerts</h2><div id="alerts" class="mute">none</div></section>
<section><h2>Nodes</h2><table id="nodes"></table></section>
<section><h2>Recommendations</h2><div id="recs" class="mute">none</div></section>
<section><h2>Tenants and queue</h2><table id="tenants"></table><p></p><table id="tasks"></table></section>
</main>
<script>
const key=new URLSearchParams(location.search).get("key")||"";
const esc=s=>String(s??"-").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const f=(v,n=0)=>v==null?"-":Number(v).toFixed(n);
const bar=v=>`<span class="bar"><i style="width:${Math.max(0,Math.min(100,v||0))}%"></i></span>${f(v)}%`;
async function tick(){
 try{
  const r=await fetch("api/state?key="+encodeURIComponent(key),{cache:"no-store"});
  if(!r.ok) throw new Error(r.status);
  const s=await r.json();
  document.getElementById("meta").textContent=`hub ${s.hub.name} · ${s.hub.role} · epoch ${s.hub.epoch} · updated ${new Date(s.ts*1000).toLocaleTimeString()}`;
  const u=s.utilization;
  document.getElementById("kpis").innerHTML=[["nodes",u.nodes],["cores",u.cores],["CPU",u.cpu_utilization_pct==null?"-":f(u.cpu_utilization_pct,1)+"%"],
   ["queued",s.queue.counts.queued||0],["running",s.queue.counts.running||0],["done",s.queue.counts.done||0],["failed",s.queue.counts.failed||0]].map(([k,v])=>`<div><b>${esc(v)}</b>${k}</div>`).join("");
  document.getElementById("nodes").innerHTML="<tr><th>node</th><th>up</th><th>cores</th><th>cpu</th><th>ram free</th><th>gpus</th><th>$/h</th><th>samples</th></tr>"+
   s.nodes.map(n=>`<tr><td>${esc(n.node)}</td><td class="${n.alive?"ok":"bad"}">${n.alive?"yes":"NO"}</td><td>${f(n.cores)}</td><td>${bar(n.cpu_avg)}</td><td>${f(n.ram_avail_pct)}%</td><td>${esc(n.gpu_count)}</td><td>${f(n.usd_per_hour,2)}</td><td>${esc(n.samples)}</td></tr>`).join("");
  const firing=Object.values(s.alerts.firing);
  const b=document.getElementById("banner");b.style.display=firing.length?"block":"none";b.textContent=firing.map(a=>a.text).join(" · ");
  document.getElementById("alerts").innerHTML=(firing.length?firing.map(a=>`<div class="bad">● ${esc(a.severity)} ${esc(a.text)}</div>`).join(""):"<span class='ok'>nothing firing</span>")+
   s.alerts.history.slice(-5).reverse().map(e=>`<div class="mute">${new Date(e.ts*1000).toLocaleTimeString()} ${esc(e.event)} ${esc(e.key)}</div>`).join("");
  document.getElementById("recs").innerHTML=s.recommendations.length?s.recommendations.map(r=>`<p><span class="tag ${r.severity=="high"?"bad":"warn"}">${esc(r.severity)}</span> <b>${esc(r.kind)}</b> ${esc(r.text)}${r.est_saving_usd_per_month?` <span class="mute">(estimated saving ${f(r.est_saving_usd_per_month)} $/month: an estimate, not a result)</span>`:""}</p>`).join(""):"no recommendation: nothing in the measurements justifies a change";
  document.getElementById("tenants").innerHTML="<tr><th>tenant</th><th>weight</th><th>finished s</th><th>weighted load</th><th>queued</th><th>running</th></tr>"+
   s.tenants.map(t=>`<tr><td>${esc(t.tenant)}</td><td>${f(t.weight,1)}</td><td>${f(t.finished_s,1)}</td><td>${f(t.weighted_load,1)}</td><td>${esc(t.queued)}</td><td>${esc(t.running)}</td></tr>`).join("");
  document.getElementById("tasks").innerHTML="<tr><th>task</th><th>workload</th><th>state</th><th>node</th><th>tenant</th><th>wall s</th></tr>"+
   s.queue.recent.map(t=>`<tr><td>${esc(t.id)}${t.gang?" (gang)":""}</td><td>${esc(t.workload)}</td><td class="${t.state=="failed"?"bad":t.state=="done"?"ok":""}">${esc(t.state)}</td><td>${esc(t.node)}</td><td>${esc(t.tenant)}</td><td>${f(t.wall_s,2)}</td></tr>`).join("");
 }catch(e){document.getElementById("meta").textContent="no data: "+e.message}
}
tick();setInterval(tick,3000);
</script></body></html>"""


class Dashboard:
    def __init__(self, hubs, token: bytes, port: int = 0, interval_s: float = 3.0, window_s: float = 60.0,
                 min_severity: str = "high", webhook: str | None = None):
        self.hubs, self.token, self.interval_s, self.window_s, self.webhook = hubs, token, interval_s, window_s, webhook
        self.alerts = AlertEngine(min_severity)
        self.key = secrets.token_urlsafe(16)
        self.state: dict = {"error": "starting"}
        self._cli = None
        self._stop = threading.Event()
        dash = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _deny(self, code, msg):
                self.send_response(code); self.send_header("Content-Type", "text/plain"); self.end_headers(); self.wfile.write(msg.encode())

            def do_GET(self):
                host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
                if host not in ("127.0.0.1", "localhost", "::1"):
                    return self._deny(403, "bad host")                 # DNS rebinding
                u = urlparse(self.path)
                k = (parse_qs(u.query).get("key") or [""])[0]
                if not secrets.compare_digest(k, dash.key):
                    return self._deny(403, "missing or wrong key")
                if u.path == "/api/state":
                    body = json.dumps(dash.state).encode(); ctype = "application/json"
                elif u.path in ("/", "/index.html"):
                    body = PAGE.encode(); ctype = "text/html; charset=utf-8"
                else:
                    return self._deny(404, "not found")
                self.send_response(200)
                self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY"); self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
                self.end_headers(); self.wfile.write(body)

            do_POST = do_PUT = do_DELETE = lambda self: self._deny(405, "read-only")

        self._http = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)    # loopback only, by construction
        self.port = self._http.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?key={self.key}"

    def refresh(self) -> dict:
        try:
            if self._cli is None:
                self._cli = connect_active(self.hubs, self.token, timeout=10)
            c = self._cli
            role = c.call({"op": "role"})[0]
            nodes = c.call({"op": "nodes", "window_s": self.window_s})[0]
            recs = c.call({"op": "advise", "window_s": self.window_s})[0]["recommendations"]
            events = self.alerts.update(recs)
            self.state = {"ts": time.time(), "hub": role, "nodes": nodes["nodes"], "utilization": nodes["utilization"],
                          "recommendations": recs, "tenants": c.call({"op": "tenants"})[0]["tenants"], "queue": c.call({"op": "queue"})[0],
                          "alerts": {"firing": self.alerts.firing, "history": self.alerts.history}}
            if self.webhook:
                for e in events:
                    try:
                        post_webhook(self.webhook, e)
                    except Exception:
                        pass
        except Exception as e:                                          # keep serving; reconnect (and fail over) next round
            if self._cli is not None:
                try: self._cli.close()
                except Exception: pass
            self._cli = None
            self.state = {**{k: v for k, v in self.state.items() if k != "error"}, "error": f"{type(e).__name__}: {e}"} if "nodes" in self.state else {"error": f"{type(e).__name__}: {e}"}
        return self.state

    def start(self) -> "Dashboard":
        def loop():
            while not self._stop.is_set():
                self.refresh()
                self._stop.wait(self.interval_s)
        threading.Thread(target=loop, daemon=True).start()
        threading.Thread(target=self._http.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._http.shutdown(); self._http.server_close()

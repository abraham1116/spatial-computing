"use strict";
/* Spatial Computing console. One file, no framework. Everything user-supplied is inserted with textContent. */
const S = {me: null, csrf: "", hub: null, payments: false, docs: "#", newKey: null, jobMsg: {}, timer: null, org: null, orgs: [], role: "owner", perms: [], sso: {enabled: false}, requireVerified: false, invite: null, ticket: null};
const can = p => (S.perms || []).includes(p);
const root = document.getElementById("root");
const NS = "http://www.w3.org/2000/svg";

/* ---------------------------------------------------------------- tiny helpers */
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat(Infinity)) if (k !== null && k !== undefined && k !== false) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
}
const svg = (tag, attrs, ...kids) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); kids.forEach(k => e.append(k.nodeType ? k : document.createTextNode(k))); return e; };
async function api(method, path, body) {
  const r = await fetch(path, {method, credentials: "same-origin", headers: {"Content-Type": "application/json", "X-CSRF-Token": S.csrf, ...(S.org ? {"X-Org": String(S.org)} : {})}, body: body ? JSON.stringify(body) : undefined});
  let data = {};
  try { data = await r.json(); } catch (e) { /* empty body */ }
  if (r.status === 401 && S.me) { S.me = null; location.hash = "#/login"; }
  if (!r.ok) throw new Error(data.error || ("request failed (" + r.status + ")"));
  return data;
}
const fmt = {
  hours: s => (s / 3600).toFixed(s < 360 ? 3 : 2) + " h",
  usd: x => "$" + (x < 1 ? x.toFixed(4) : x.toFixed(2)),
  date: t => t ? new Date(t * 1000).toLocaleDateString(undefined, {year: "numeric", month: "short", day: "numeric"}) : "never",
  time: t => new Date(t * 1000).toLocaleString(),
  secs: s => s === null || s === undefined ? "-" : s < 1 ? (s * 1000).toFixed(0) + " ms" : s.toFixed(2) + " s",
};
function toast(msg) { const t = h("div", {class: "toast", role: "status"}, msg); document.body.append(t); setTimeout(() => t.remove(), 3500); }
async function copy(text) { try { await navigator.clipboard.writeText(text); toast("Copied"); } catch (e) { toast("Copy failed: select the text and copy it"); } }
const val = id => document.getElementById(id).value;
const showErr = (msg, id = "err") => { const e = document.getElementById(id); if (e) e.textContent = msg; };
async function guarded(ev, fn, errId = "err") {
  ev.preventDefault(); showErr("", errId);
  const b = ev.target.querySelector("button[type=submit]"); if (b) b.disabled = true;
  try { await fn(); } catch (e) { showErr(e.message, errId); } finally { if (b) b.disabled = false; }
}
const field = (label, id, type = "text", extra = {}) => [h("label", {for: id}, label), h("input", {id, name: id, type, required: extra.required !== false, autocomplete: extra.autocomplete || "off", ...extra})];
const kpi = (value, label) => h("div", {}, h("b", {}, value), h("span", {}, label));
const tag = (text, cls) => h("span", {class: "tag " + (cls || "mute")}, text);
const th = cols => h("thead", {}, h("tr", {}, ...cols.map(x => h("th", {}, x))));
const docLink = (path, text) => h("a", {href: S.docs.replace(/index\.html.*$/, "") + path, target: "_blank", rel: "noopener"}, text);
const empty = (title, text, action) => h("div", {class: "empty"}, h("h3", {}, title), h("p", {}, text), action || null);

function modal(title, body, onClose) {
  const d = h("dialog", {class: "modal"}, h("div", {class: "mhead"}, h("h2", {}, title), h("button", {class: "btn ghost sm", type: "button", onclick: () => d.close()}, "Close")), body);
  d.addEventListener("close", () => { d.remove(); if (onClose) onClose(); });
  document.body.append(d); d.showModal(); return d;
}

/* ---------------------------------------------------------------- reusable pieces */
function newAppDialog(go = true) {
  const form = h("form", {onsubmit: ev => guarded(ev, async () => {
      const b = val("na_budget"); const r = await api("POST", "/api/apps", {name: val("na_name"), description: val("na_desc"), budget_usd: b === "" ? null : Number(b)});
      d.close(); toast("App created"); location.hash = "#/apps/" + r.app.id; if (!go) route();
    }, "na_err")},
    ...field("App name", "na_name", "text", {maxlength: 60, placeholder: "my-inference-service"}),
    h("label", {for: "na_desc"}, "Description (optional)"), h("input", {id: "na_desc", maxlength: 300}),
    h("label", {for: "na_budget"}, "Monthly budget in USD (optional)"), h("input", {id: "na_budget", type: "number", min: 0, step: "0.01", placeholder: "no limit"}),
    h("p", {class: "err", id: "na_err", role: "alert"}), h("button", {class: "btn", type: "submit"}, "Create app"));
  const d = modal("New app", form); document.getElementById("na_name").focus(); return d;
}
function newKeyDialog(apps, preApp) {
  if (!apps.length) { toast("Create an app first"); return newAppDialog(); }
  const form = h("form", {onsubmit: ev => guarded(ev, async () => {
      const r = await api("POST", `/api/apps/${val("nk_app")}/keys`, {name: val("nk_name"), kind: val("nk_kind"), ttl_days: Number(val("nk_ttl"))});
      S.newKey = {app: Number(val("nk_app")), token: r.key.token, kind: r.key.kind}; d.close(); route();
    }, "nk_err")},
    h("label", {for: "nk_app"}, "App"), h("select", {id: "nk_app"}, apps.map(a => h("option", {value: a.id, selected: preApp === a.id}, a.name))),
    ...field("Key name", "nk_name", "text", {maxlength: 60, placeholder: "production"}),
    h("label", {for: "nk_kind"}, "Type"), h("select", {id: "nk_kind"}, h("option", {value: "client"}, "client: submit work and read results"), h("option", {value: "node"}, "node: lets a machine join the fleet")),
    ...field("Lifetime (days)", "nk_ttl", "number", {min: 1, max: 365, value: 90}),
    h("p", {class: "err", id: "nk_err", role: "alert"}), h("button", {class: "btn", type: "submit"}, "Create key"));
  const d = modal("New API key", form); document.getElementById("nk_name").focus(); return d;
}
function revealKey() {
  if (!S.newKey) return null;
  const hub = S.hub || "HUB_HOST:PORT";
  const use = S.newKey.kind === "node" ? `spatial agent --hub ${hub} --token-file node.tok` : `spatial fleet submit --hub ${hub} --token-file app.tok --workload montecarlo_pi --params '{"samples":1000000}'`;
  return h("div", {class: "reveal", role: "alert"}, h("b", {}, "Copy your " + S.newKey.kind + " key now. It is shown only once."), h("code", {}, S.newKey.token),
    h("p", {class: "small"}, "Save it to a file, then: ", h("span", {class: "mono"}, use)),
    h("div", {class: "row"}, h("button", {class: "btn sm", onclick: () => copy(S.newKey.token)}, "Copy key"), h("button", {class: "btn ghost sm", onclick: () => { S.newKey = null; route(); }}, "I saved it")));
}
function keysTable(keys, withApp) {
  return h("table", {}, th([withApp ? "App" : null, "Name", "Type", "Key", "Created", "Expires", "Status", ""].filter(Boolean)),
    h("tbody", {}, keys.map(k => h("tr", {}, withApp ? h("td", {}, h("a", {href: "#/apps/" + k.app_id}, k.app)) : null, h("td", {}, k.name), h("td", {}, tag(k.kind, k.kind === "node" ? "warn" : "mute")), h("td", {class: "mono"}, "…" + k.hint),
      h("td", {}, fmt.date(k.created)), h("td", {}, fmt.date(k.expires)), h("td", {}, k.revoked ? tag("revoked", "bad") : tag("active", "ok")),
      h("td", {}, k.revoked ? null : h("button", {class: "btn danger sm", onclick: async () => { if (confirm("Revoke key “" + k.name + "”? Programs using it stop working at once.")) { await api("DELETE", `/api/apps/${k.app_id}/keys/${k.id}`); route(); } }}, "Revoke"))))));
}
function chart(byDay, days) {
  const today = new Date(); const map = Object.fromEntries(byDay.map(x => [x.day, x]));
  const list = []; for (let i = days - 1; i >= 0; i--) { const d = new Date(today.getTime() - i * 86400000).toISOString().slice(0, 10); list.push(map[d] || {day: d, seconds: 0, tasks: 0}); }
  const W = 720, H = 160, pad = 28, max = Math.max(1, ...list.map(x => x.seconds)), bw = (W - pad) / list.length;
  const s = svg("svg", {class: "chart", viewBox: `0 0 ${W} ${H + 24}`, role: "img", "aria-label": "Compute seconds per day"});
  [0, .5, 1].forEach(f => s.append(svg("line", {x1: pad, x2: W, y1: H - f * (H - 10), y2: H - f * (H - 10)})));
  s.append(svg("text", {x: 0, y: 14}, max >= 60 ? (max / 60).toFixed(1) + "m" : max.toFixed(1) + "s"));
  list.forEach((x, i) => { const hh = x.seconds / max * (H - 10); const r = svg("rect", {class: "bar", x: pad + i * bw + 1, y: H - hh, width: Math.max(1, bw - 2), height: Math.max(x.seconds > 0 ? 1 : 0, hh)}); r.append(svg("title", {}, x.day + ": " + x.tasks + " tasks, " + x.seconds.toFixed(2) + " s")); s.append(r); });
  [0, list.length - 1].forEach(i => s.append(svg("text", {x: pad + i * bw, y: H + 16, "text-anchor": i ? "end" : "start"}, list[i].day.slice(5))));
  return s;
}
const stateTag = st => tag(st, st === "done" ? "ok" : st === "failed" ? "bad" : st === "running" ? "warn" : "mute");
function jobsTable(rows) {
  return rows.length ? h("table", {}, th(["Task", "App", "Workload", "State", "Node", "Duration"]),
    h("tbody", {}, rows.map(t => h("tr", {}, h("td", {}, "#" + t.id + (t.gang ? " (gang)" : "")), h("td", {}, t.app || t.tenant), h("td", {}, t.workload), h("td", {}, stateTag(t.state)), h("td", {class: "mono small"}, t.node || "-"), h("td", {}, fmt.secs(t.wall_s)))))) : h("p", {class: "mute"}, "No job yet.");
}

/* ---------------------------------------------------------------- auth screens */
function authScreen(title, lead, form, alt) {
  return h("div", {class: "auth"},
    h("div", {class: "brand"}, h("div", {class: "logo"}, h("img", {src: "/logo.svg", alt: ""}), "Spatial Computing"),
      h("div", {}, h("h2", {}, "Run every job where it costs least."), h("p", {class: "q"}, "Create an app, get an API key, send work to the fleet. Pay only for the compute you use.")),
      h("div", {class: "stats"}, h("div", {}, h("b", {}, "12 / 12"), "planner decisions right"), h("div", {}, h("b", {}, "6.7 s"), "hub failover"), h("div", {}, h("b", {}, "AES-256"), "encrypted links"))),
    h("div", {class: "form"}, h("div", {}, h("form", {onsubmit: form.submit, novalidate: true}, h("h1", {}, title), h("p", {class: "mute"}, lead), ...form.fields,
      h("p", {class: "err", id: "err", role: "alert"}), h("button", {class: "btn", type: "submit"}, form.button), h("p", {class: "alt"}, alt)))));
}
const ssoError = () => { const m = /sso_error=([^&]*)/.exec(location.hash); return m ? decodeURIComponent(m[1]) : ""; };
const loginView = () => authScreen("Sign in", "Welcome back.", {
  fields: [...field("E-mail", "email", "email", {autocomplete: "username"}), ...field("Password", "password", "password", {autocomplete: "current-password"})], button: "Sign in",
  submit: ev => guarded(ev, async () => { const d = await api("POST", "/api/login", {email: val("email"), password: val("password")}); if (d.needs_2fa) { S.ticket = d.ticket; location.hash = "#/2fa"; route(); return; } await afterAuth(); })},
  [h("a", {href: "#/forgot"}, "Forgot your password?"), "  ·  ", h("a", {href: "#/signup"}, "Create an account"),
    S.sso.enabled ? h("div", {class: "ssorow"}, h("a", {class: "btn ghost", href: "/api/sso/start"}, "Sign in with " + S.sso.name)) : null,
    ssoError() ? h("p", {class: "err", role: "alert"}, ssoError()) : null]);
const twofaView = () => authScreen("Two-factor code", "Enter the 6-digit code from your authenticator app, or one of your recovery codes.", {
  fields: field("Code", "code", "text", {autocomplete: "one-time-code", inputmode: "numeric", maxlength: 24}), button: "Verify",
  submit: ev => guarded(ev, async () => { try { await api("POST", "/api/login/2fa", {ticket: S.ticket, code: val("code")}); S.ticket = null; await afterAuth(); } catch (e) { if (/expired/.test(e.message)) { S.ticket = null; location.hash = "#/login"; } throw e; } })},
  [h("a", {href: "#/login"}, "Start again")]);
const signupView = () => authScreen("Create your account", "A free monthly allowance is included. No card needed.", {
  fields: [...field("Name", "name", "text", {autocomplete: "name", maxlength: 80}), ...field("E-mail", "email", "email", {autocomplete: "username"}), ...field("Password (10 characters or more)", "password", "password", {autocomplete: "new-password", minlength: 10})], button: "Create account",
  submit: ev => guarded(ev, async () => { await api("POST", "/api/signup", {name: val("name"), email: val("email"), password: val("password")}); await afterAuth(); })},
  ["Already have an account? ", h("a", {href: "#/login"}, "Sign in")]);
const forgotView = () => authScreen("Reset your password", "We will send you a link, valid for one hour.", {
  fields: field("E-mail", "email", "email", {autocomplete: "username"}), button: "Send the link",
  submit: ev => guarded(ev, async () => { const d = await api("POST", "/api/password/reset-request", {email: val("email")}); const e = document.getElementById("err"); e.className = "okmsg"; e.textContent = d.message; })}, [h("a", {href: "#/login"}, "Back to sign in")]);
const resetView = token => authScreen("Choose a new password", "Use at least 10 characters.", {
  fields: field("New password", "password", "password", {autocomplete: "new-password", minlength: 10}), button: "Save password",
  submit: ev => guarded(ev, async () => { await api("POST", "/api/password/reset", {token, password: val("password")}); toast("Password changed: sign in"); location.hash = "#/login"; })}, [h("a", {href: "#/login"}, "Back to sign in")]);

/* ---------------------------------------------------------------- shell */
function orgSwitcher() {
  const sel = h("select", {class: "orgsel", "aria-label": "Organization", onchange: async ev => {
    if (ev.target.value === "new") { ev.target.value = String(S.org); const name = prompt("Name of the new organization"); if (!name) return;
      try { const r = await api("POST", "/api/orgs", {name}); localStorage.setItem("sp_org", r.org.id); loadSession(await api("GET", "/api/me")); location.hash = "#/team"; route(); } catch (e) { toast(e.message); } return; }
    localStorage.setItem("sp_org", ev.target.value); loadSession(await api("GET", "/api/me")); location.hash = "#/"; route(); }},
    S.orgs.map(o => h("option", {value: o.id, selected: o.id === S.org}, (o.personal ? "Personal: " : "") + o.name)), h("option", {value: "new"}, "+ New organization"));
  return sel;
}
function shell(active, ...content) {
  const link = (href, label, key) => h("a", {class: "nav" + (active === key ? " on" : ""), href}, label);
  const unverified = S.requireVerified && !S.me.email_verified && !S.me.is_admin;
  return h("div", {class: "shell"},
    h("aside", {class: "side"}, h("div", {class: "logo"}, h("img", {src: "/logo.svg", alt: ""}), "Console"), orgSwitcher(),
      link("#/", "Overview", "overview"), link("#/apps", "Apps", "apps"), link("#/jobs", "Jobs", "jobs"), link("#/fleet", "Fleet", "fleet"),
      link("#/keys", "API keys", "keys"), link("#/team", "Team", "team"), can("billing.read") ? link("#/billing", "Usage & billing", "billing") : null, link("#/settings", "Settings", "settings"),
      S.me.is_admin ? link("#/admin", "Admin", "admin") : null,
      h("a", {class: "nav ext", href: S.docs, target: "_blank", rel: "noopener"}, "Documentation ↗"),
      h("div", {class: "grow"}), h("div", {class: "me"}, S.me.name, h("br"), S.me.email),
      h("a", {class: "nav", href: "#/", onclick: async ev => { ev.preventDefault(); await api("POST", "/api/logout"); S.me = null; location.hash = "#/login"; }}, "Sign out")),
    h("main", {class: "main"}, unverified ? h("div", {class: "notice"}, "Confirm your e-mail address to create API keys and run jobs: open the link we sent you. ",
      h("button", {class: "btn ghost sm", onclick: async () => { try { await api("POST", "/api/verify/resend"); toast("Sent again"); } catch (e) { toast(e.message); } }}, "Send it again")) : null, ...content));
}
const pageTop = (title, lead, ...actions) => h("div", {class: "top"}, h("div", {}, h("h1", {}, title), lead ? h("p", {class: "mute"}, lead) : null), h("div", {class: "row"}, ...actions));
const newAppBtn = () => h("button", {class: "btn", onclick: () => newAppDialog()}, "New app");

/* ---------------------------------------------------------------- overview */
async function overviewView() {
  const [o, a] = await Promise.all([api("GET", "/api/overview"), api("GET", "/api/apps")]);
  const done = o.checklist.filter(c => c.done).length;
  const actions = {app: () => newAppDialog(), key: () => location.hash = "#/keys", node: () => location.hash = "#/fleet", job: () => location.hash = "#/jobs"};
  const labels = {app: "Create app", key: "Create key", node: "Connect", job: "Run a job"};
  const check = done < o.checklist.length ? h("div", {class: "card mark"}, h("h2", {}, "Get started: " + done + " of " + o.checklist.length),
    h("ol", {class: "steps"}, o.checklist.map(c => h("li", {class: c.done ? "done" : ""}, h("div", {}, h("b", {}, c.title), h("p", {class: "mute small"}, c.hint)),
      c.done ? tag("done", "ok") : h("button", {class: "btn sm", onclick: actions[c.key]}, labels[c.key]))))) : null;
  return shell("overview",
    pageTop("Hello, " + S.me.name.split(" ")[0] + ".", "Your infrastructure at a glance, for " + o.period + ".", newAppBtn()),
    check,
    h("div", {class: "kpis"}, kpi(o.apps, "apps"), kpi(o.keys, "active API keys"), kpi(o.nodes_up + " / " + o.nodes_total, "nodes up"), kpi(o.tasks_this_month, "tasks this month"), kpi(fmt.hours(o.compute_hours_this_month * 3600), "compute this month"), kpi(fmt.usd(o.estimated_usd), "estimated charge")),
    a.apps.length ? h("div", {class: "card"}, h("div", {class: "cardhead"}, h("h2", {}, "Apps"), h("a", {href: "#/apps"}, "All apps →")), appsTable(a.apps)) : null,
    h("div", {class: "card"}, h("h2", {}, "What each part of the console does"),
      h("div", {class: "grid3"}, ...[["Apps", "A project: its own keys, usage and budget.", "console.html"], ["Jobs", "Submit work and follow it.", "fleet.html"], ["Fleet", "The machines that joined with your node keys.", "fleet.html"],
        ["API keys", "Client keys send work, node keys add machines.", "console.html"], ["Usage & billing", "Metered compute, invoices, payment.", "console.html"], ["Settings", "Profile, sessions, account tokens for the REST API.", "api.html"]]
        .map(([t, d, p]) => h("div", {}, h("b", {}, t), h("p", {class: "mute small"}, d, " ", docLink("docs/" + p, "Docs"))))),
      h("p", {class: "small mute"}, "The engines behind it (planner, accelerators, interconnect, operations) are described in the ", docLink("docs/index.html", "documentation"), ".")));
}
function appsTable(apps) {
  return h("table", {}, th(["App", "Keys", "Compute this month", "Budget", ""]),
    h("tbody", {}, apps.map(a => h("tr", {}, h("td", {}, h("a", {href: "#/apps/" + a.id}, a.name)), h("td", {}, a.keys.filter(k => !k.revoked).length), h("td", {}, fmt.hours(a.month_seconds)),
      h("td", {}, a.budget_usd === null ? h("span", {class: "mute"}, "none") : [fmt.usd(a.budget_usd), " ", a.over_budget ? tag("reached", "bad") : null]), h("td", {}, h("a", {class: "btn ghost sm", href: "#/apps/" + a.id}, "Open"))))));
}

/* ---------------------------------------------------------------- apps */
async function appsView() {
  const d = await api("GET", "/api/apps");
  return shell("apps", pageTop("Apps", "Each app has its own API keys, usage and optional budget.", newAppBtn()),
    d.apps.length ? h("div", {class: "card"}, appsTable(d.apps)) : empty("No app yet", "An app is a project that talks to the infrastructure with its own keys.", newAppBtn()));
}
const TABS = [["", "Overview"], ["keys", "Keys"], ["connect", "Connect"], ["jobs", "Jobs"], ["settings", "Settings"]];
async function appView(id, tab) {
  const {app} = await api("GET", "/api/apps/" + id);
  const tabs = h("nav", {class: "tabs"}, TABS.map(([k, l]) => h("a", {href: "#/apps/" + id + (k ? "/" + k : ""), class: (tab || "") === k ? "on" : ""}, l)));
  const head = [h("div", {class: "crumbs"}, h("a", {href: "#/apps"}, "Apps"), " / " + app.name),
    pageTop(app.name, app.description || "", h("span", {class: "mono small mute"}, "tenant " + app.tenant)), app.over_budget ? h("div", {class: "notice"}, "This app reached its monthly budget (" + fmt.usd(app.budget_usd) + "). New jobs are refused until next month or until you raise it.") : null, tabs];
  let body;
  if (!tab) {
    const usage = await api("GET", `/api/apps/${id}/usage?days=30`);
    body = [h("div", {class: "kpis"}, kpi(usage.tasks, "tasks, last 30 days"), kpi(fmt.hours(usage.seconds), "compute, last 30 days"), kpi(fmt.hours(app.month_seconds), "compute this month"), kpi(app.keys.filter(k => !k.revoked).length, "active keys")),
      h("div", {class: "card"}, h("h2", {}, "Usage"), usage.tasks ? chart(usage.by_day, 30) : h("p", {class: "mute"}, "No usage yet. Run a job from the Jobs tab or send work with an API key.")),
      usage.recent.length ? h("div", {class: "card"}, h("h2", {}, "Recent tasks"), h("table", {}, th(["When", "Workload", "Node", "Duration", "Result"]),
        h("tbody", {}, usage.recent.map(r => h("tr", {}, h("td", {}, fmt.time(r.ts)), h("td", {}, r.workload), h("td", {class: "mono small"}, r.node), h("td", {}, fmt.secs(r.seconds)), h("td", {}, tag(r.ok ? "ok" : "failed", r.ok ? "ok" : "bad"))))))) : null];
  } else if (tab === "keys") {
    body = [revealKey(), h("div", {class: "card"}, h("div", {class: "cardhead"}, h("h2", {}, "API keys"), h("button", {class: "btn", onclick: () => newKeyDialog([{id: app.id, name: app.name}], app.id)}, "New key")),
      app.keys.length ? keysTable(app.keys.map(k => ({...k, app_id: app.id, app: app.name})), false) : h("p", {class: "mute"}, "No key yet."),
      h("p", {class: "small mute"}, "A key is shown once, when it is created; only its last four characters are kept. Revoking stops it on the running hub at once. ", docLink("docs/console.html", "How keys map to the hub")))];
  } else if (tab === "connect") {
    const hub = S.hub || "HUB_HOST:PORT";
    body = [h("div", {class: "grid2"},
      h("div", {class: "card"}, h("h2", {}, "Send work"), h("p", {class: "small mute"}, "Hub address: ", h("span", {class: "mono"}, hub)),
        h("pre", {class: "code"}, `# put a client key in app.tok, then:\nspatial fleet submit --hub ${hub} \\\n  --token-file app.tok \\\n  --workload montecarlo_pi \\\n  --params '{"samples": 1000000}'\n\nspatial fleet status --hub ${hub} --token-file app.tok`)),
      h("div", {class: "card"}, h("h2", {}, "Add a machine"), h("p", {class: "small mute"}, "Create a node key (Keys tab), save it to node.tok on the machine, then:"),
        h("pre", {class: "code"}, `pip install "spatial-computing[quantum]"\nspatial agent --hub ${hub} --token-file node.tok`), h("p", {class: "small mute"}, "The machine appears in ", h("a", {href: "#/fleet"}, "Fleet"), " within seconds."))),
      h("div", {class: "card"}, h("h2", {}, "From Python"), h("pre", {class: "code"}, `from spatial.core.protocol import RpcClient\nc = RpcClient("${hub.split(":")[0]}", ${hub.split(":")[1] || 7700}, open("app.tok","rb").read().strip())\ntid = c.call({"op": "submit", "workload": "montecarlo_pi", "params": {"samples": 1000000}})[0]["task_id"]\nprint(c.call({"op": "task", "task_id": tid})[0]["task"]["state"])`),
        h("p", {class: "small mute"}, docLink("docs/fleet.html", "Fleet documentation"), " · ", docLink("docs/api.html", "REST API for the console")))];
  } else if (tab === "jobs") {
    body = [await jobsPanel(app.id)];
  } else {
    body = [h("div", {class: "card"}, h("h2", {}, "Settings"), h("form", {onsubmit: ev => guarded(ev, async () => { const b = val("s_budget"); await api("PATCH", "/api/apps/" + id, {name: val("s_name"), description: val("s_desc"), budget_usd: b === "" ? null : Number(b)}); toast("Saved"); route(); })},
        ...field("Name", "s_name", "text", {maxlength: 60, value: app.name}), h("label", {for: "s_desc"}, "Description"), h("input", {id: "s_desc", maxlength: 300, value: app.description}),
        h("label", {for: "s_budget"}, "Monthly budget in USD (empty = no limit)"), h("input", {id: "s_budget", type: "number", min: 0, step: "0.01", value: app.budget_usd === null ? "" : app.budget_usd}),
        h("p", {class: "err", id: "err", role: "alert"}), h("button", {class: "btn", type: "submit"}, "Save"))),
      h("div", {class: "card"}, h("h2", {}, "Delete this app"), h("p", {class: "mute"}, "Revokes every key of the app. Usage already metered stays on your invoices."),
        h("button", {class: "btn danger", onclick: async () => { if (confirm("Delete app “" + app.name + "” and revoke all its keys?")) { await api("DELETE", "/api/apps/" + id); toast("App deleted"); location.hash = "#/apps"; } }}, "Delete app"))];
  }
  return shell("apps", ...head, ...body);
}

/* ---------------------------------------------------------------- jobs */
async function jobsPanel(onlyApp) {
  const [apps, wl, fl] = await Promise.all([api("GET", "/api/apps"), api("GET", "/api/workloads"), api("GET", "/api/fleet")]);
  const out = h("div", {class: "mono small", id: "jobout"}, S.jobMsg.last || "");
  const params = h("div", {id: "jparams"});
  const renderParams = () => {
    const w = wl.workloads.find(x => x.name === val("j_wl")); params.replaceChildren();
    for (const p of w.params) params.append(h("div", {class: "pfield"}, h("label", {for: "p_" + p.name}, p.name + " (" + p.min + " to " + p.max + ")"), h("input", {id: "p_" + p.name, "data-p": p.name, type: "number", min: p.min, max: p.max, step: "any", value: p.default})));
    document.getElementById("jdoc").textContent = w.doc || "";
  };
  const form = h("form", {onsubmit: ev => guarded(ev, async () => {
      const body = {}; document.querySelectorAll("#jparams input").forEach(i => { if (i.value !== "") body[i.dataset.p] = isNaN(Number(i.value)) ? i.value : Number(i.value); });
      const r = await api("POST", `/api/apps/${val("j_app")}/jobs`, {workload: val("j_wl"), params: body});
      S.jobMsg.last = "submitted: task #" + r.task_id + " (queued). It appears below as soon as a node takes it."; out.textContent = S.jobMsg.last; setTimeout(route, 1200);
    }, "j_err")},
    h("div", {class: "row"}, h("div", {}, h("label", {for: "j_app"}, "App"), h("select", {id: "j_app"}, apps.apps.map(a => h("option", {value: a.id, selected: onlyApp === a.id}, a.name)))),
      h("div", {}, h("label", {for: "j_wl"}, "Workload"), h("select", {id: "j_wl", onchange: renderParams}, wl.workloads.map(w => h("option", {value: w.name}, w.title))))),
    h("p", {class: "small mute", id: "jdoc"}), params, h("p", {class: "err", id: "j_err", role: "alert"}), h("button", {class: "btn", type: "submit"}, "Submit job"), h("p", {}), out);
  const rows = fl.queue.recent.filter(t => !onlyApp || t.tenant === "app" + onlyApp);
  if (rows.some(t => t.state === "queued" || t.state === "running")) { clearTimeout(S.timer); S.timer = setTimeout(route, 2500); }
  const el = h("div", {},
    !apps.apps.length ? empty("Create an app first", "Jobs run under an app, with its keys, usage and budget.", newAppBtn()) : h("div", {class: "card"}, h("h2", {}, "Submit a job"), h("p", {class: "mute small"}, "Runs one of the hub's allow-listed workloads on your fleet. It is metered like any other task."), form),
    !fl.reachable ? h("div", {class: "notice"}, "The hub is not reachable from the console: jobs cannot be listed or submitted right now.") : null,
    h("div", {class: "card"}, h("h2", {}, "Recent jobs"), jobsTable(rows), fl.nodes.filter(n => n.alive).length ? null : h("p", {class: "small mute"}, "No node of yours is online: queued jobs wait until one connects (", h("a", {href: "#/fleet"}, "add a machine"), ").")));
  if (apps.apps.length) setTimeout(renderParams, 0);
  return el;
}
async function jobsView() { return shell("jobs", pageTop("Jobs", "Submit work to your fleet and follow it."), await jobsPanel(null)); }

/* ---------------------------------------------------------------- fleet */
async function fleetView() {
  const [fl, a] = await Promise.all([api("GET", "/api/fleet"), api("GET", "/api/apps")]);
  const hub = S.hub || "HUB_HOST:PORT";
  const c = fl.queue.counts || {};
  return shell("fleet", pageTop("Fleet", "The machines that joined with your node keys, and the work waiting for them.", h("button", {class: "btn", onclick: () => newKeyDialog(a.apps)}, "New node key")),
    revealKey(),
    h("div", {class: "kpis"}, kpi(fl.reachable ? "reachable" : "unreachable", "hub " + hub), kpi(fl.nodes.filter(n => n.alive).length + " / " + fl.nodes.length, "nodes up"), kpi(c.queued || 0, "queued"), kpi(c.running || 0, "running"), kpi(c.done || 0, "done"), kpi(c.failed || 0, "failed")),
    h("div", {class: "card"}, h("h2", {}, "Nodes"), fl.nodes.length ? h("table", {}, th(["Node (key)", "App", "Status", "Cores", "CPU", "RAM free", "GPUs"]),
      h("tbody", {}, fl.nodes.map(n => h("tr", {}, h("td", {class: "mono small"}, n.node), h("td", {}, h("a", {href: "#/apps/" + n.app_id}, n.app)), h("td", {}, n.alive ? tag("up", "ok") : tag("down", "bad")), h("td", {}, n.cores), h("td", {}, n.cpu_percent === null ? "-" : n.cpu_percent.toFixed(0) + "%"), h("td", {}, n.ram_free_percent === null ? "-" : n.ram_free_percent.toFixed(0) + "%"), h("td", {}, n.gpus)))))
      : empty("No machine yet", "Create a node key, then run the agent on a machine.", h("pre", {class: "code"}, `spatial agent --hub ${hub} --token-file node.tok`))),
    h("div", {class: "card"}, h("h2", {}, "Recent jobs"), jobsTable(fl.queue.recent.slice(0, 10)), h("p", {class: "small mute"}, h("a", {href: "#/jobs"}, "All jobs →"), "  ·  ", docLink("docs/fleet.html", "How placement works"), "  ·  ", docLink("docs/operations.html", "Failover, persistence, scale"))));
}

/* ---------------------------------------------------------------- API keys */
async function keysView() {
  const a = await api("GET", "/api/apps");
  const all = a.apps.flatMap(x => x.keys.map(k => ({...k, app_id: x.id, app: x.name})));
  return shell("keys", pageTop("API keys", "Hub credentials, per app. A client key sends work; a node key lets a machine join.", h("button", {class: "btn", onclick: () => newKeyDialog(a.apps)}, "New key")),
    revealKey(),
    h("div", {class: "card"}, all.length ? keysTable(all, true) : empty("No key yet", "Create an app, then a key.", a.apps.length ? h("button", {class: "btn", onclick: () => newKeyDialog(a.apps)}, "New key") : newAppBtn()),
      h("p", {class: "small mute"}, "Keys are for the infrastructure (the hub). To call this console's REST API from a script, use an ", h("a", {href: "#/settings/tokens"}, "account token"), ". ", docLink("docs/console.html", "Documentation"))));
}

/* ---------------------------------------------------------------- team */
async function teamView() {
  const {org} = await api("GET", "/api/org");
  const isAdmin = can("members.manage") || can("org.manage"), canMembers = can("members.manage"), isOwner = can("org.delete");
  const roleNames = org.roles.map(r => r.name).filter(n => n !== "owner" || isOwner);
  const apps = org.app_list || [];
  const pickedApps = id => [...document.querySelectorAll("#" + id + " input:checked")].map(i => Number(i.value));
  const appPicker = (id, chosen) => h("div", {id, class: "perms"}, apps.map(a => h("label", {class: "check"}, h("input", {type: "checkbox", value: a.id, checked: chosen ? chosen.includes(a.id) : false}), " ", a.name)));
  const inviteForm = canMembers && !org.personal ? h("form", {onsubmit: ev => guarded(ev, async () => { const sc = document.getElementById("iv_scope"), only = sc && sc.checked; const body = {email: val("iv_email"), role: val("iv_role")}; if (only) body.apps = pickedApps("iv_apps"); await api("POST", "/api/org/invites", body); toast("Invitation sent"); route(); }, "iv_err")},
    h("div", {class: "row"}, h("div", {}, ...field("E-mail", "iv_email", "email", {placeholder: "colleague@example.com"})),
      h("div", {}, h("label", {for: "iv_role"}, "Role"), h("select", {id: "iv_role"}, roleNames.map(r => h("option", {value: r, selected: r === "member"}, r)))),
      h("div", {}, h("label", {}, " "), h("button", {class: "btn", type: "submit"}, "Invite"))),
    apps.length ? h("div", {}, h("label", {class: "check"}, h("input", {type: "checkbox", id: "iv_scope", onchange: ev => { document.getElementById("iv_apps_wrap").hidden = !ev.target.checked; }}), " Only some apps"), h("div", {hidden: true, id: "iv_apps_wrap"}, appPicker("iv_apps", []))) : null,
    h("p", {class: "err", id: "iv_err", role: "alert"})) : null;
  const scopeCell = m => {
    const label = m.apps ? (m.apps.length ? m.apps.map(id => (apps.find(a => a.id === id) || {name: "#" + id}).name).join(", ") : "none") : "all apps";
    if (!canMembers || !apps.length || m.role === "owner") return h("span", {class: "small " + (m.apps ? "" : "mute")}, label);
    return h("details", {}, h("summary", {class: "small"}, label), appPicker("sc_" + m.user_id, m.apps || apps.map(a => a.id)),
      h("button", {class: "btn ghost sm", onclick: async () => { try { await api("PATCH", "/api/org/members/" + m.user_id, {apps: pickedApps("sc_" + m.user_id)}); toast("Apps updated"); route(); } catch (e) { toast(e.message); } }}, "Limit to these"),
      m.apps ? h("button", {class: "btn ghost sm", onclick: async () => { try { await api("PATCH", "/api/org/members/" + m.user_id, {apps: null}); toast("Access to all apps"); route(); } catch (e) { toast(e.message); } }}, "All apps") : null);
  };
  const roleSel = m => canMembers && m.user_id !== S.me.id ? h("select", {onchange: async ev => { try { await api("PATCH", "/api/org/members/" + m.user_id, {role: ev.target.value}); toast("Role changed"); route(); } catch (e) { toast(e.message); route(); } }},
    roleNames.map(r => h("option", {value: r, selected: r === m.role}, r))) : tag(m.role, m.role === "owner" ? "warn" : "mute");
    return shell("team", pageTop(org.name, org.personal ? "Your personal workspace: one member. Create an organization to work with others." : "Members, roles and invitations."),
    h("div", {class: "card"}, h("div", {class: "cardhead"}, h("h2", {}, "Members (" + org.member_list.length + ")")),
      h("table", {}, th(["Name", "E-mail", "Role", "Apps", "Since", ""]), h("tbody", {}, org.member_list.map(m => h("tr", {}, h("td", {}, m.name), h("td", {class: "mono small"}, m.email), h("td", {}, roleSel(m)), h("td", {}, scopeCell(m)), h("td", {}, fmt.date(m.since)),
        h("td", {}, (canMembers && m.user_id !== S.me.id) || (m.user_id === S.me.id && !org.personal) ? h("button", {class: "btn danger sm", onclick: async () => { if (confirm(m.user_id === S.me.id ? "Leave this organization?" : "Remove " + m.name + "?")) { try { await api("DELETE", "/api/org/members/" + m.user_id); if (m.user_id === S.me.id) { localStorage.removeItem("sp_org"); loadSession(await api("GET", "/api/me")); location.hash = "#/"; } route(); } catch (e) { toast(e.message); } } }}, m.user_id === S.me.id ? "Leave" : "Remove") : null))))),
      h("p", {class: "small mute"}, docLink("docs/console.html", "Roles are explained in the documentation"))),
    canMembers && !org.personal ? h("div", {class: "card"}, h("h2", {}, "Invite someone"), inviteForm,
      (org.invites || []).length ? h("table", {}, th(["Pending invitation", "Role", "Expires", ""]), h("tbody", {}, org.invites.map(i => h("tr", {}, h("td", {}, i.email), h("td", {}, tag(i.role)), h("td", {}, fmt.date(i.expires)), h("td", {}, h("button", {class: "btn ghost sm", onclick: async () => { await api("DELETE", "/api/org/invites/" + i.id); route(); }}, "Cancel")))))) : null) : null,
    h("div", {class: "card"}, h("h2", {}, "Roles and permissions"), h("p", {class: "small mute"}, "Everyone in the organization can read apps, usage, fleet and jobs. Everything else is a permission. Nobody can give a role with permissions they do not have themselves."),
      h("table", {}, th(["Role", "Permissions", "Members", ""]), h("tbody", {}, org.roles.map(r => h("tr", {}, h("td", {}, tag(r.name, r.builtin ? "mute" : "warn")), h("td", {class: "small"}, r.perms.length ? r.perms.map(p => h("span", {class: "pill", title: org.permission_help[p]}, p)) : h("span", {class: "mute"}, "read only")),
        h("td", {}, r.builtin ? "" : r.members), h("td", {}, !r.builtin && canMembers ? h("button", {class: "btn danger sm", onclick: async () => { try { await api("DELETE", "/api/org/roles/" + r.name); route(); } catch (e) { toast(e.message); } }}, "Delete") : null))))),
      canMembers ? h("form", {onsubmit: ev => guarded(ev, async () => { const perms = [...document.querySelectorAll("#rl_perms input:checked")].map(i => i.value); await api("POST", "/api/org/roles", {name: val("rl_name"), perms}); toast("Role created"); route(); }, "rl_err")},
        h("h3", {}, "New role"), h("div", {class: "row"}, h("div", {}, ...field("Name", "rl_name", "text", {maxlength: 30, placeholder: "billing-clerk"}))),
        h("div", {id: "rl_perms", class: "perms"}, Object.entries(org.permission_help).filter(([p]) => p !== "org.delete" && p !== "members.owner" && org.perms.includes(p)).map(([p, d]) => h("label", {class: "check"}, h("input", {type: "checkbox", value: p}), " ", h("span", {class: "mono small"}, p), " ", h("span", {class: "mute small"}, "— " + d)))),
        h("p", {class: "err", id: "rl_err", role: "alert"}), h("button", {class: "btn", type: "submit"}, "Create role")) : null),
    isAdmin ? h("div", {class: "card"}, h("h2", {}, "Organization"), h("form", {onsubmit: ev => guarded(ev, async () => { await api("PATCH", "/api/org", {name: val("on_name")}); toast("Saved"); loadSession(await api("GET", "/api/me")); route(); }, "on_err")},
        ...field("Name", "on_name", "text", {maxlength: 60, value: org.name}), h("p", {class: "err", id: "on_err", role: "alert"}), h("button", {class: "btn", type: "submit"}, "Save")),
      isOwner && !org.personal ? h("p", {}, h("button", {class: "btn danger", onclick: async () => { if (confirm("Delete organization “" + org.name + "” with its apps, keys and usage?")) { try { await api("DELETE", "/api/org"); localStorage.removeItem("sp_org"); loadSession(await api("GET", "/api/me")); location.hash = "#/"; route(); } catch (e) { toast(e.message); } } }}, "Delete organization")) : null) : null);
}

/* ---------------------------------------------------------------- billing */
async function billingView() {
  const [b, od] = await Promise.all([api("GET", "/api/billing"), api("GET", "/api/org")]);
  const p = b.pricing, e = b.estimate, bd = od.org.billing || {};
  const pay = inv => h("button", {class: "btn sm", disabled: !b.payments_enabled, title: b.payments_enabled ? "" : "Payments are not configured on this server", onclick: async () => { try { const r = await api("POST", "/api/billing/pay", {invoice_id: inv.id}); location.href = r.url; } catch (er) { toast(er.message); } }}, "Pay " + fmt.usd(inv.amount_usd));
  const details = h("form", {onsubmit: ev => guarded(ev, async () => { await api("PATCH", "/api/org", {billing: {name: val("bd_name"), address: val("bd_addr"), country: val("bd_country"), vat_id: val("bd_vat"), city: val("bd_city"), postal_code: val("bd_postal"), email: val("bd_email")}}); toast("Billing details saved"); route(); }, "bd_err")},
    h("div", {class: "grid2"}, h("div", {}, ...field("Company or name on invoices", "bd_name", "text", {required: false, maxlength: 120, value: bd.name || ""}), ...field("VAT id (optional)", "bd_vat", "text", {required: false, maxlength: 40, value: bd.vat_id || ""}), bd.vat_status ? h("p", {class: "small mute"}, "VAT id: ", tag(bd.vat_status, "ok")) : null),
      h("div", {}, ...field("Country (2 letters)", "bd_country", "text", {required: false, maxlength: 2, value: bd.country || "", placeholder: "FR"}), h("label", {for: "bd_addr"}, "Address"), h("textarea", {id: "bd_addr", rows: 3, maxlength: 400}, bd.address || ""),
      ...field("Postal code", "bd_postal", "text", {required: false, maxlength: 20, value: bd.postal_code || ""}), ...field("City", "bd_city", "text", {required: false, maxlength: 80, value: bd.city || ""}), ...field("Billing e-mail", "bd_email", "email", {required: false, value: bd.email || ""}))),
    h("p", {class: "err", id: "bd_err", role: "alert"}), h("button", {class: "btn", type: "submit"}, "Save billing details"));
  return shell("billing", pageTop("Usage & billing", "Pay for what you use. Usage is metered per finished task."),
    b.payments_enabled ? null : h("div", {class: "notice"}, "Payments are not configured on this server: invoices are shown, but nothing can be charged."),
    b.pricing_is_default ? h("div", {class: "notice"}, "The operator has not set real prices yet: these are example prices.") : null,
    h("div", {class: "kpis"}, kpi(fmt.usd(e.total_usd), "estimated for " + b.period + (e.tax_rate ? " (incl. " + e.tax_label + " " + e.tax_rate + "%)" : "")), kpi(p.free_compute_hours_per_month + " h", "free compute per month"), kpi(fmt.usd(p.compute_usd_per_hour), "per compute hour after that")),
    h("div", {class: "card"}, h("h2", {}, "This month by app"), e.lines.length ? h("table", {}, th(["App", "Compute", "Billable", "Amount"]),
      h("tbody", {}, e.lines.map(l => h("tr", {}, h("td", {}, l.app), h("td", {}, fmt.hours(l.seconds)), h("td", {}, fmt.hours(l.billable_seconds)), h("td", {}, fmt.usd(l.usd))))),
      h("tfoot", {}, h("tr", {}, h("td", {colspan: 3, class: "mute"}, "Subtotal"), h("td", {}, fmt.usd(e.subtotal_usd))), e.tax_rate ? h("tr", {}, h("td", {colspan: 3, class: "mute"}, e.tax_label + " " + e.tax_rate + "%"), h("td", {}, fmt.usd(e.tax_usd))) : null,
        h("tr", {}, h("td", {colspan: 3}, h("b", {}, "Total")), h("td", {}, h("b", {}, fmt.usd(e.total_usd)))))) : h("p", {class: "mute"}, "No usage this month."), e.tax_note ? h("p", {class: "small mute"}, e.tax_note) : null),
    h("div", {class: "card"}, h("h2", {}, "Invoices"), b.invoices.length ? h("table", {}, th(["Number", "Period", "Amount", "Status", "", ""]),
      h("tbody", {}, b.invoices.map(i => h("tr", {}, h("td", {class: "mono small"}, i.number || "-"), h("td", {}, i.period), h("td", {}, fmt.usd(i.amount_usd)), h("td", {}, tag(i.status, i.status === "paid" ? "ok" : i.status === "open" ? "warn" : "mute")),
        h("td", {}, i.number ? h("a", {class: "btn ghost sm", href: "/api/invoices/" + i.id + "/pdf?org=" + S.org, download: i.number + ".pdf"}, "PDF") : null, i.number ? h("a", {class: "btn ghost sm", href: "/api/invoices/" + i.id + "/ubl?org=" + S.org, download: i.number + ".xml", title: "UBL 2.1 e-invoice (XML)"}, "XML") : null), h("td", {}, i.status === "open" ? pay(i) : null))))) : h("p", {class: "mute"}, "No invoice yet. Invoices are created when a month with usage ends."),
      h("p", {class: "small mute"}, docLink("docs/console.html", "How billing works"))),
    b.credit_notes && b.credit_notes.length ? h("div", {class: "card"}, h("h2", {}, "Credit notes"), h("table", {}, th(["Number", "Date", "Amount", "Reason", "State", ""]),
      h("tbody", {}, b.credit_notes.map(n => h("tr", {}, h("td", {class: "mono small"}, n.number), h("td", {}, fmt.date(n.created)), h("td", {}, "-" + fmt.usd(n.total_usd)), h("td", {class: "small"}, n.reason), h("td", {}, tag(n.status, n.status === "refunded" || n.status === "applied" ? "ok" : "warn")),
        h("td", {}, h("a", {class: "btn ghost sm", href: "/api/credit-notes/" + n.id + "/pdf?org=" + S.org, download: n.number + ".pdf"}, "PDF"), h("a", {class: "btn ghost sm", href: "/api/credit-notes/" + n.id + "/ubl?org=" + S.org, download: n.number + ".xml", title: "UBL 2.1 credit note (XML)"}, "XML"))))))) : null,
    h("div", {class: "card"}, h("h2", {}, "Billing details"), h("p", {class: "mute small"}, "Printed on invoices; the country and VAT id decide the tax rate. A VAT id is checked for format and, where the algorithm is public, the check digit."), can("org.manage") ? details : h("p", {class: "mute"}, "Only people who can manage the organization edit these.")));
}

/* ---------------------------------------------------------------- settings */
function twofaCard() {
  const box = h("div", {});
  const render = async () => {
    box.replaceChildren();
    if (S.me.totp_enabled) {
      box.append(h("p", {}, tag("on", "ok"), " Sign-in needs a code from your authenticator app, or a recovery code."),
        h("form", {onsubmit: ev => guarded(ev, async () => { await api("POST", "/api/2fa/disable", {password: val("tf_pw"), code: val("tf_code")}); S.me.totp_enabled = false; S.me = null; toast("Two-factor sign-in turned off: sign in again"); location.hash = "#/login"; route(); }, "tf_err")},
          h("div", {class: "row"}, h("div", {}, ...field("Password", "tf_pw", "password", {autocomplete: "current-password"})), h("div", {}, ...field("Code or recovery code", "tf_code", "text", {autocomplete: "one-time-code"})), h("div", {}, h("label", {}, " "), h("button", {class: "btn danger", type: "submit"}, "Turn off"))),
          h("p", {class: "err", id: "tf_err", role: "alert"})));
    } else if (S.tf && S.tf.secret) {
      box.append(h("p", {class: "small mute"}, "1. In your authenticator app (Google Authenticator, 1Password, Aegis…) scan this code, or add an account by hand with the key below:"),
        h("div", {class: "row"}, h("img", {class: "qr", alt: "QR code to scan with your authenticator app", width: 200, height: 200, src: "data:image/svg+xml;base64," + btoa(S.tf.qr_svg)}), h("pre", {class: "code"}, S.tf.secret)), h("p", {class: "small mute"}, "2. Enter the 6-digit code it shows:"),
        h("form", {onsubmit: ev => guarded(ev, async () => { const r = await api("POST", "/api/2fa/enable", {code: val("tf_code")}); S.me.totp_enabled = true; S.tf = null; S.recovery = r.recovery_codes; route(); }, "tf_err")},
          h("div", {class: "row"}, h("div", {}, ...field("Code", "tf_code", "text", {inputmode: "numeric", maxlength: 6, autocomplete: "one-time-code"})), h("div", {}, h("label", {}, " "), h("button", {class: "btn", type: "submit"}, "Turn on"))), h("p", {class: "err", id: "tf_err", role: "alert"})));
    } else {
      box.append(h("p", {class: "mute"}, "Off. Protect your account with a code from an authenticator app in addition to your password."),
        h("button", {class: "btn", onclick: async () => { try { S.tf = await api("POST", "/api/2fa/setup"); render(); } catch (e) { toast(e.message); } }}, "Set up"));
    }
    if (S.recovery) box.prepend(h("div", {class: "reveal", role: "alert"}, h("b", {}, "Save your recovery codes now. They are shown only once; each works once."), h("code", {}, S.recovery.join("   ")),
      h("div", {class: "row"}, h("button", {class: "btn sm", onclick: () => copy(S.recovery.join("\n"))}, "Copy"), h("button", {class: "btn ghost sm", onclick: () => { S.recovery = null; render(); }}, "I saved them"))));
  };
  render(); return h("div", {class: "card"}, h("h2", {}, "Two-factor sign-in"), box);
}
const SET_TABS = [["", "Profile"], ["security", "Security"], ["tokens", "Account tokens"], ["activity", "Activity"], ["data", "Data"]];
async function settingsView(tab) {
  const tabs = h("nav", {class: "tabs"}, SET_TABS.map(([k, l]) => h("a", {href: "#/settings" + (k ? "/" + k : ""), class: (tab || "") === k ? "on" : ""}, l)));
  let body;
  if (!tab) {
    body = [h("div", {class: "card"}, h("h2", {}, "Profile"), h("p", {class: "mute small"}, "E-mail: ", h("span", {class: "mono"}, S.me.email), " · member since " + fmt.date(S.me.created)),
      h("form", {onsubmit: ev => guarded(ev, async () => { const r = await api("PATCH", "/api/me", {name: val("pname")}); S.me = r.user; toast("Saved"); route(); })}, ...field("Name", "pname", "text", {maxlength: 80, value: S.me.name}), h("p", {class: "err", id: "err", role: "alert"}), h("button", {class: "btn", type: "submit"}, "Save")))];
  } else if (tab === "security") {
    const ss = await api("GET", "/api/sessions");
    body = [twofaCard(), h("div", {class: "card"}, h("h2", {}, "Password"), h("form", {onsubmit: ev => guarded(ev, async () => { await api("POST", "/api/password/change", {current: val("cur"), new: val("new")}); toast("Password changed; other sessions were signed out"); route(); })},
        ...field("Current password", "cur", "password", {autocomplete: "current-password"}), ...field("New password (10 characters or more)", "new", "password", {autocomplete: "new-password", minlength: 10}), h("p", {class: "err", id: "err", role: "alert"}), h("button", {class: "btn", type: "submit"}, "Change password"))),
      h("div", {class: "card"}, h("h2", {}, "Active sessions"), h("table", {}, th(["Signed in", "Browser", "Address", "", ""]), h("tbody", {}, ss.sessions.map(x => h("tr", {}, h("td", {}, fmt.time(x.created)), h("td", {class: "small"}, x.agent || "-"), h("td", {class: "mono small"}, x.ip || "-"),
        h("td", {}, x.current ? tag("this browser", "ok") : null), h("td", {}, x.current ? null : h("button", {class: "btn danger sm", onclick: async () => { await api("DELETE", "/api/sessions/" + x.id); route(); }}, "Sign out"))))))) ];
  } else if (tab === "tokens") {
    const t = await api("GET", "/api/tokens");
    const reveal = S.newToken ? h("div", {class: "reveal", role: "alert"}, h("b", {}, "Copy your token now. It is shown only once."), h("code", {}, S.newToken),
      h("p", {class: "small"}, "Use it: ", h("span", {class: "mono"}, `curl -H "Authorization: Bearer ${S.newToken.slice(0, 10)}…" ${location.origin}/api/apps`)), h("div", {class: "row"}, h("button", {class: "btn sm", onclick: () => copy(S.newToken)}, "Copy token"), h("button", {class: "btn ghost sm", onclick: () => { S.newToken = null; route(); }}, "I saved it"))) : null;
    body = [reveal, h("div", {class: "card"}, h("h2", {}, "Account tokens"), h("p", {class: "mute small"}, "For scripts that call this console's REST API (create apps, keys, read usage). Not hub credentials: those are the API keys. ", docLink("docs/api.html", "REST API reference")),
      h("form", {onsubmit: ev => guarded(ev, async () => { const r = await api("POST", "/api/tokens", {name: val("tname"), scope: val("tscope"), ttl_days: Number(val("tttl"))}); S.newToken = r.token.token; route(); })},
        h("div", {class: "row"}, h("div", {}, ...field("Name", "tname", "text", {maxlength: 60, placeholder: "ci"})), h("div", {}, h("label", {for: "tscope"}, "Scope"), h("select", {id: "tscope"}, h("option", {value: "read"}, "read: GET only"), h("option", {value: "write"}, "write: also create and change"))),
          h("div", {}, ...field("Lifetime (days)", "tttl", "number", {min: 1, max: 365, value: 90})), h("div", {}, h("label", {}, " "), h("button", {class: "btn", type: "submit"}, "Create token"))), h("p", {class: "err", id: "err", role: "alert"})),
      t.tokens.length ? h("table", {}, th(["Name", "Scope", "Token", "Created", "Expires", "Last used", "Status", ""]), h("tbody", {}, t.tokens.map(x => h("tr", {}, h("td", {}, x.name), h("td", {}, tag(x.scope, x.scope === "write" ? "warn" : "mute")), h("td", {class: "mono"}, "spt_…" + x.hint), h("td", {}, fmt.date(x.created)), h("td", {}, fmt.date(x.expires)), h("td", {}, fmt.date(x.last_used)),
        h("td", {}, x.revoked ? tag("revoked", "bad") : tag("active", "ok")), h("td", {}, x.revoked ? null : h("button", {class: "btn danger sm", onclick: async () => { if (confirm("Revoke token “" + x.name + "”?")) { await api("DELETE", "/api/tokens/" + x.id); route(); } }}, "Revoke")))))) : h("p", {class: "mute"}, "No token yet."))];
  } else if (tab === "activity") {
    const a = await api("GET", "/api/activity");
    body = [h("div", {class: "card"}, h("h2", {}, "Security activity"), a.activity.length ? h("table", {}, th(["When", "Event", "Detail"]), h("tbody", {}, a.activity.map(e => h("tr", {}, h("td", {}, fmt.time(e.ts)), h("td", {class: "mono small"}, e.kind), h("td", {class: "mono small"}, e.detail || ""))))) : h("p", {class: "mute"}, "Nothing yet."))];
  } else {
    body = [h("div", {class: "card"}, h("h2", {}, "Export your data"), h("p", {class: "mute"}, "Everything the service holds about you, as JSON (no secrets)."), h("a", {class: "btn ghost", href: "/api/export", download: "spatial-account-export.json"}, "Download export")),
      h("div", {class: "card"}, h("h2", {}, "Delete your account"), h("p", {class: "mute"}, "Deletes your apps, keys, usage, invoices and sessions, and revokes every key. Blocked while an invoice is open."),
        h("form", {onsubmit: ev => guarded(ev, async () => { if (!confirm("Delete your account for good?")) return; await api("DELETE", "/api/me", {password: val("dpw")}); S.me = null; location.hash = "#/signup"; })},
          ...field("Your password", "dpw", "password", {autocomplete: "current-password"}), h("p", {class: "err", id: "err", role: "alert"}), h("button", {class: "btn danger", type: "submit"}, "Delete account")))];
  }
  return shell("settings", pageTop("Settings", ""), tabs, ...body);
}

/* ---------------------------------------------------------------- admin */
async function adminView() {
  const [o, u, st, mail, invs] = await Promise.all([api("GET", "/api/admin/overview"), api("GET", "/api/admin/users"), api("GET", "/api/admin/settings"), api("GET", "/api/admin/mail"), api("GET", "/api/admin/invoices")]);
  const hub = o.hub, p = st.pricing, co = st.company;
  const pricing = h("form", {onsubmit: ev => guarded(ev, async () => {
      let by = {}; try { by = val("pr_by").trim() ? JSON.parse(val("pr_by")) : {}; } catch (e) { throw new Error('Tax by country must be JSON, for example {"FR": 20, "DE": 19}'); }
      await api("PUT", "/api/admin/pricing", {currency: val("pr_cur"), compute_usd_per_hour: Number(val("pr_rate")), free_compute_hours_per_month: Number(val("pr_free")), min_invoice_usd: Number(val("pr_min")),
        tax_label: val("pr_label"), tax_rate_percent: Number(val("pr_tax")), tax_by_country: by, no_tax_with_vat_id_abroad: document.getElementById("pr_rc").checked}); toast("Prices saved (invoices already issued do not change)"); route(); }, "pr_err")},
    h("div", {class: "grid3"}, h("div", {}, ...field("Price per compute hour", "pr_rate", "number", {step: "any", min: 0, max: 1000, value: p.compute_usd_per_hour})), h("div", {}, ...field("Free compute hours per month", "pr_free", "number", {step: "any", min: 0, value: p.free_compute_hours_per_month})),
      h("div", {}, ...field("Minimum invoice", "pr_min", "number", {step: "any", min: 0, value: p.min_invoice_usd})), h("div", {}, ...field("Currency (3 letters)", "pr_cur", "text", {maxlength: 3, value: p.currency})),
      h("div", {}, ...field("Tax name", "pr_label", "text", {maxlength: 20, value: p.tax_label})), h("div", {}, ...field("Default tax rate %", "pr_tax", "number", {step: "any", min: 0, max: 50, value: p.tax_rate_percent}))),
    h("label", {for: "pr_by"}, "Tax rate by customer country (JSON)"), h("input", {id: "pr_by", value: JSON.stringify(p.tax_by_country || {})}),
    h("label", {class: "check"}, h("input", {type: "checkbox", id: "pr_rc", checked: !!p.no_tax_with_vat_id_abroad}), " No tax for a customer with a VAT id in another country than yours (simplified reverse charge)"),
    h("p", {class: "err", id: "pr_err", role: "alert"}), h("button", {class: "btn", type: "submit"}, "Save prices"));
  const coKeys = ["name", "address", "city", "postal_code", "vat_id", "country", "email", "registration_no", "legal_form", "share_capital", "tax_no", "iban", "bic", "payment_terms_days", "legal_footer", "tax_exempt_note"];
  const coOpt = {required: false};
  const company = h("form", {onsubmit: ev => guarded(ev, async () => { const body = {}; coKeys.forEach(k => body[k] = val("co_" + k)); await api("PUT", "/api/admin/company", body); toast("Company details saved"); route(); }, "co_err")},
    h("div", {class: "grid2"},
      h("div", {}, ...field("Legal name", "co_name", "text", {...coOpt, value: co.name}), ...field("Legal form (SAS, GmbH, Ltd...)", "co_legal_form", "text", {...coOpt, maxlength: 40, value: co.legal_form || ""}),
        ...field("Company registration number (SIREN, HRB...)", "co_registration_no", "text", {...coOpt, value: co.registration_no || ""}), ...field("Share capital", "co_share_capital", "text", {...coOpt, value: co.share_capital || ""}),
        ...field("VAT id", "co_vat_id", "text", {...coOpt, value: co.vat_id}), ...field("National tax number (if no VAT id)", "co_tax_no", "text", {...coOpt, value: co.tax_no || ""})),
      h("div", {}, h("label", {for: "co_address"}, "Address"), h("textarea", {id: "co_address", rows: 3, maxlength: 400}, co.address),
        ...field("Postal code", "co_postal_code", "text", {...coOpt, value: co.postal_code || ""}), ...field("City", "co_city", "text", {...coOpt, value: co.city || ""}),
        ...field("Country (2 letters)", "co_country", "text", {...coOpt, maxlength: 2, value: co.country}), ...field("Contact e-mail", "co_email", "email", {...coOpt, value: co.email}))),
    h("h3", {}, "Payment and legal text"),
    h("div", {class: "grid2"}, h("div", {}, ...field("IBAN", "co_iban", "text", {...coOpt, value: co.iban || ""}), ...field("BIC", "co_bic", "text", {...coOpt, value: co.bic || ""}), ...field("Payment terms (days)", "co_payment_terms_days", "number", {...coOpt, min: 0, max: 120, value: co.payment_terms_days})),
      h("div", {}, h("label", {for: "co_legal_footer"}, "Extra legal text (footer)"), h("textarea", {id: "co_legal_footer", rows: 3, maxlength: 400}, co.legal_footer || ""),
        ...field("Reason when no tax is charged", "co_tax_exempt_note", "text", {...coOpt, maxlength: 200, value: co.tax_exempt_note || ""}))),
    h("p", {class: "small mute"}, "Required fields depend on your country (the warnings above name what is missing). This is a checklist, not legal advice."),
    h("p", {class: "err", id: "co_err", role: "alert"}), h("button", {class: "btn", type: "submit"}, "Save company details"));
  const testMail = h("form", {onsubmit: ev => guarded(ev, async () => { const r = await api("POST", "/api/admin/test-mail", {to: val("tm_to")}); toast(r.sent ? "Test message sent" : "Not sent: " + (r.error || "see the queue below")); route(); }, "tm_err")},
    h("div", {class: "row"}, h("div", {}, ...field("Send a test message to", "tm_to", "email", {value: S.me.email})), h("div", {}, h("label", {}, " "), h("button", {class: "btn", type: "submit", disabled: !st.email.smtp_configured}, "Send test"))), h("p", {class: "err", id: "tm_err", role: "alert"}));
  return shell("admin", pageTop("Admin", "The platform as a whole. Visible to the first account only."),
    ...(st.warnings || []).map(w => h("div", {class: "notice"}, w)),
    h("div", {class: "kpis"}, kpi(o.users, "users"), kpi(o.apps, "apps"), kpi(o.active_keys, "active keys"), kpi(o.tasks_this_month, "tasks this month"), kpi(o.compute_hours_this_month.toFixed(2) + " h", "compute this month"), kpi(fmt.usd(o.open_invoices_usd), "open invoices")),
    h("div", {class: "grid2"}, h("div", {class: "card"}, h("h2", {}, "Hub"), hub.reachable ? h("table", {}, h("tbody", {}, [["Address", hub.address], ["Role", hub.role + " (epoch " + hub.epoch + ")"], ["Nodes up", hub.nodes_up + " / " + hub.nodes], ["Queue", Object.entries(hub.queue || {}).map(([k, v]) => k + " " + v).join(", ") || "empty"]].map(([k, v]) => h("tr", {}, h("td", {class: "mute"}, k), h("td", {}, v))))) : h("p", {class: "mute"}, "Hub not reachable from the console."), h("p", {class: "small mute"}, docLink("docs/operations.html", "Operations: failover, scale, dashboard"))),
      h("div", {class: "card"}, h("h2", {}, "Services"), h("table", {}, h("tbody", {}, [["Payments", st.payments_enabled ? "Stripe configured" : "not configured (invoices cannot be charged)"], ["E-mail", st.email.smtp_configured ? "SMTP configured" : "not configured: messages stay in the queue"], ["E-mail verification", st.email.require_verified ? "required before keys and jobs" : "not required"], ["Unsent e-mails", st.email.unsent]].map(([k, v]) => h("tr", {}, h("td", {class: "mute"}, k), h("td", {}, v))))), h("p", {class: "small mute"}, docLink("docs/console.html", "Deploying the console")))),
    h("div", {class: "card"}, h("h2", {}, "Prices and tax"), h("p", {class: "mute small"}, "Applies to usage from now on. Invoices already issued keep the prices they were issued with."), pricing),
    h("div", {class: "card"}, h("h2", {}, "Company (printed on invoices)"), company),
    h("div", {class: "card"}, h("h2", {}, "Invoices and credit notes"), invs.invoices.length ? h("table", {}, th(["Number", "Customer", "Period", "Total", "Credited", "State", ""]),
      h("tbody", {}, invs.invoices.map(i => h("tr", {}, h("td", {class: "mono small"}, i.number), h("td", {}, i.org), h("td", {}, i.period), h("td", {}, fmt.usd(i.total_usd)), h("td", {}, i.credited_usd ? fmt.usd(i.credited_usd) : "-"), h("td", {}, tag(i.status, i.status === "paid" ? "ok" : i.status === "open" ? "warn" : "mute")),
        h("td", {}, h("button", {class: "btn ghost sm", onclick: async () => { const a = prompt("Amount to credit (subtotal, before tax) for " + i.number); if (!a) return; const r = prompt("Reason (shown on the credit note)"); if (!r) return; try { const n = await api("POST", "/api/admin/invoices/" + i.id + "/credit", {amount_usd: Number(a), reason: r}); toast(n.credit_note.number + " (" + n.credit_note.status + ")"); route(); } catch (e) { toast(e.message); } }}, "Credit")))))) : h("p", {class: "mute"}, "No numbered invoice yet.")),
    h("div", {class: "card"}, h("h2", {}, "E-mail"), testMail, mail.mail.length ? h("table", {}, th(["When", "To", "Subject", "State"]), h("tbody", {}, mail.mail.map(m => h("tr", {}, h("td", {}, fmt.time(m.created)), h("td", {class: "mono small"}, m.to), h("td", {}, m.subject), h("td", {}, m.sent ? tag("sent", "ok") : m.attempts ? tag("retrying (" + m.attempts + ")", "warn") : tag("queued", "mute")))))) : h("p", {class: "mute"}, "No message yet.")),
    h("div", {class: "card"}, h("h2", {}, "Users (" + u.total + ")"), h("table", {}, th(["E-mail", "Name", "Apps", "Compute this month", "Joined", ""]), h("tbody", {}, u.users.map(x => h("tr", {}, h("td", {}, x.email), h("td", {}, x.name), h("td", {}, x.apps), h("td", {}, x.compute_hours_this_month.toFixed(3) + " h"), h("td", {}, fmt.date(x.created)), h("td", {}, x.is_admin ? tag("admin", "warn") : x.locked ? tag("locked", "bad") : null)))))));
}

/* ---------------------------------------------------------------- router */
async function route() {
  clearTimeout(S.timer);
  const hash = location.hash.replace(/^#/, "") || "/"; const authed = !!S.me; let view;
  try {
    if (hash.startsWith("/2fa/")) { S.ticket = hash.slice(5); view = twofaView(); }
    else if (hash === "/signup") view = authed ? (location.hash = "#/", null) : signupView();
    else if (hash === "/login" || hash.startsWith("/login?")) view = authed ? (location.hash = "#/", null) : loginView();
    else if (hash === "/forgot") view = forgotView();
    else if (hash === "/2fa") view = S.ticket ? twofaView() : loginView();
    else if (hash.startsWith("/verify/")) { try { const r = await api("POST", "/api/verify", {token: hash.slice(8)}); if (S.me) S.me = r.user; toast("E-mail confirmed"); } catch (e) { toast(e.message); } location.hash = authed ? "#/" : "#/login"; return; }
    else if (hash.startsWith("/invite/")) { S.invite = hash.slice(8); location.hash = authed ? "#/" : "#/signup"; if (authed) await afterAuth(); else toast("Sign in or create an account with the address that was invited"); return; }
    else if (hash.startsWith("/reset/")) view = resetView(hash.slice(7));
    else if (!authed) { location.hash = "#/login"; return; }
    else if (hash === "/") view = await overviewView();
    else if (hash === "/apps") view = await appsView();
    else if (/^\/apps\/\d+(\/\w+)?$/.test(hash)) { const p = hash.split("/"); view = await appView(p[2], p[3]); }
    else if (hash === "/jobs") view = await jobsView();
    else if (hash === "/fleet") view = await fleetView();
    else if (hash === "/keys") view = await keysView();
    else if (hash === "/team") view = await teamView();
    else if (hash.startsWith("/billing")) view = await billingView();
    else if (/^\/settings(\/\w+)?$/.test(hash)) view = await settingsView(hash.split("/")[2]);
    else if (hash === "/admin") view = await adminView();
    else view = shell("", empty("Page not found", "", h("a", {class: "btn ghost", href: "#/"}, "Overview")));
  } catch (e) {
    view = authed ? shell("", h("div", {class: "notice"}, e.message), h("a", {class: "btn ghost", href: "#/"}, "Back to overview")) : loginView();
  }
  if (view) { root.replaceChildren(view); const f = root.querySelector(".auth input"); if (f) f.focus(); }
}
window.addEventListener("hashchange", route);
function loadSession(d) {
  S.me = d.user; S.csrf = d.csrf || ""; S.hub = d.hub; S.payments = d.payments; S.docs = d.docs || "#";
  if (d.user) { S.orgs = d.orgs || []; S.requireVerified = !!d.require_verified; const saved = Number(localStorage.getItem("sp_org") || 0);
    S.org = (S.orgs.find(o => o.id === saved) || S.orgs[0] || {}).id || d.org; S.role = (S.orgs.find(o => o.id === S.org) || {}).role || d.role || "owner"; S.perms = d.perms || []; }
}
async function afterAuth() {
  const d = await api("GET", "/api/me"); loadSession(d);
  if (S.invite) { const t = S.invite; S.invite = null; try { const r = await api("POST", "/api/invites/accept", {token: t}); localStorage.setItem("sp_org", r.org.id); toast("You joined " + r.org.name); const d2 = await api("GET", "/api/me"); loadSession(d2); } catch (e) { toast(e.message); } }
  location.hash = "#/"; route();
}
(async () => {
  try { loadSession(await api("GET", "/api/me")); } catch (e) { /* signed out */ }
  try { S.sso = await api("GET", "/api/sso/config"); } catch (e) { /* no SSO */ }
  route();
})();

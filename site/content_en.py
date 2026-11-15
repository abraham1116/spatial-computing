"""English content for the site (served at the root). Scaffolding lives in scaffold.py."""
from scaffold import CFG, E, OUT, REPO, ROOT, alt_url, doc, head, nav, out_block
import scaffold as S

NAV_GROUPS = [
    ("Get started", [("index", "Overview"), ("quickstart", "Installation")]),
    ("Engines", [("fleet", "Fleet"), ("compute", "Compute Engine"), ("memory", "Tiered memory"), ("runtime", "Runtime Engine"), ("spatialq", "SPATIAL Q")]),
    ("Reference", [("cli", "Commands"), ("security", "Security"), ("results", "Results"), ("limits", "Limitations")]),
]
UI = {"nav_label": "Main", "proof": "Proof", "install": "Install", "docs_label": "Documentation", "examples_label": "Examples"}

INSTALL = """python3 -m venv .venv && source .venv/bin/activate
pip install "spatial-computing[quantum]"
spatial audit
spatial status"""

RUN_FLEET = 'spatial token init --master-key-file hub.key\nspatial serve hub --master-key-file hub.key --port 7700\nspatial token issue --master-key-file hub.key --name node-1 --scopes fleet:report,fleet:work > node-1.tok\nspatial token issue --master-key-file hub.key --name ops --scopes fleet:read,fleet:submit > ops.tok\n# on every machine\nspatial agent --hub HUB:7700 --token-file node-1.tok --usd-per-hour 1.5\n# the operator\nspatial fleet status --hub HUB:7700 --token-file ops.tok\nspatial fleet advise --hub HUB:7700 --token-file ops.tok\nspatial fleet submit --hub HUB:7700 --token-file ops.tok --workload mandel_numba --params \'{"n":1400,"iters":300}\''
FLEET_STATUS = 'node     up  cores cpu% ramfree%\nagent-0  yes     4   48       43\nagent-1  yes     4   50       43\nagent-2  yes     4   52       43\nfleet: 3 nodes, 12 cores,\nCPU utilization 50.1%\n(last 6 s)'

BELL = open(ROOT.parent / "examples/01_bell.sq").read().strip()


def landing():
    alt = alt_url(False, "index")
    audit = "\n".join(OUT["audit"].splitlines()[:8])
    p = [head("Spatial Computing — Measure. Decide. Prove.",
              "Spatial Computing chooses where and how a workload should run from measurements, and claims a gain only when it is measured.", "", alt)]
    p.append("<body>" + nav("", "home", alt))
    p.append(f'''<main>
<div class="hero grid-bg"><div class="wrap">
<div>
<p class="eyebrow">Compute infrastructure optimization · v0.9.0 · open source</p>
<h1>Measure.<br>Decide.<br><em>Prove.</em></h1>
<p class="sub">One platform for compute infrastructure: an agent on every machine, a hub that sees the fleet, and engines for compute, memory, runtime, quantum, AI, science, simulation and holography. Measure, place, prove.</p>
<pre class="install" id="inst" tabindex="0"><button class="copy" data-copy="inst" type="button">Copy</button>{E(INSTALL)}</pre>
<div class="cta"><a class="btn" href="docs/quickstart.html">Get started</a><a class="btn ghost" href="#proof">See the measurements</a></div>
</div>
<div class="term" aria-label="Real output of the spatial audit command"><div class="bar"><i></i><i></i><i></i><span style="margin-left:8px">$ spatial audit</span></div>
<pre><span class="d">{E(audit)}</span>
<span class="g">…</span></pre></div>
</div></div>

<section id="engines"><div class="wrap">
<p class="eyebrow">One core, a fleet layer, every engine</p>
<h2>Every engine shares the same model.</h2>
<p class="lead">A resource, a task, a measurement, a cost. Spatial Core gives the fleet layer and all engines the same data model, the same encrypted protocol and the same tamper-evident ledger, so a quantum kernel, a simulation step and a memory page are scheduled and accounted for in the same way.</p>
<div class="core"><span>Spatial Core</span><i>model · protocol · ledger · registry</i></div>
</div></section>

<section id="proof"><div class="wrap">
<p class="eyebrow">Measured, not promised</p>
<h2>One proof per engine.</h2>
<p class="lead">Each figure comes from a test or a benchmark in the repository, run on a 2017 MacBook Pro (two cores, 16 GB). Reproduce them with <code>pytest</code> and <code>spatial bench all</code>.</p>
<div class="eng">
<div class="card"><h3>Fleet</h3><p>Sees every machine from one place and places work on them.</p><div class="pf"><b>×1.66</b><span>12 tasks on 3 agents against 1, placed by the hub; identical results, audit chain intact (one machine, 2 cores)</span></div></div>
<div class="card"><h3>Compute</h3><p>Runs a computation the cheapest way the machine allows.</p><div class="pf"><b>×31.6</b><span>JIT over pure Python, identical result</span></div></div>
<div class="card"><h3>Tiered memory</h3><p>Works on more data than local RAM holds, at a measured latency price.</p><div class="pf"><b>−75 %</b><span>local RAM on skewed access, for 107× mean latency</span></div></div>
<div class="card"><h3>Runtime</h3><p>Runs software built for another system, isolated.</p><div class="pf"><b>0.88 s</b><span>to boot a Linux micro-VM; a Windows .exe runs under Wine</span></div></div>
<div class="card"><h3>SPATIAL Q</h3><p>One language for classical, distributed and quantum steps.</p><div class="pf"><b>1.000</b><span>fidelity against Qiskit up to 16 qubits; a Bell pair has run on a real IBM QPU (90 % correlated)</span></div></div>
<div class="card"><h3>AI</h3><p>Reuses inference context instead of recomputing it.</p><div class="pf"><b>exact</b><span>restored KV cache gives the same output as recompute (toy model, CPU)</span></div></div>
<div class="card"><h3>Scientific</h3><p>Runs a numerical job and checks its answer.</p><div class="pf"><b>2 / 2</b><span>jobs validated against their exact solutions</span></div></div>
<div class="card"><h3>Simulation</h3><p>Steps physical systems forward.</p><div class="pf"><b>&lt; 0.1 %</b><span>energy drift over 400 N-body steps</span></div></div>
<div class="card"><h3>Intelligence</h3><p>Predicts the best strategy before running it.</p><div class="pf"><b>confirmed</b><span>prediction from past runs matched the measured winner</span></div></div>
<div class="card"><h3>Holographic</h3><p>Computes holograms for future displays.</p><div class="pf"><b>in focus</b><span>numerical reconstruction lands on the emitted points (no display hardware)</span></div></div>
</div>
<p class="note">Honest scope: one machine. Nothing is proven yet on a second machine or a data-center GPU, and quantum hardware has run one two-qubit circuit only; the AI, scientific, simulation, intelligence and holographic engines are first components, not products.</p>
</div></section>

<section><div class="wrap">
<p class="eyebrow">How it works</p>
<h2>One loop, three verbs.</h2>
<p class="lead">Every run produces a measurement. Every choice is logged with its reason. A result that differs from the reference is rejected.</p>
<div class="cols3">
<div><h3>Measure</h3><p>Detects the real hardware, watches CPU, RAM, compressor and swap, and says what it cannot do.</p><pre class="mini">$ spatial audit</pre></div>
<div><h3>Decide</h3><p>Compares execution strategies and routes (native, micro-VM, WASM) and explains every refusal.</p><pre class="mini">$ spatial plan app.exe
[ ] wine  Wine is not installed</pre></div>
<div><h3>Prove</h3><p>Replays the benchmarks, regenerates the results table and keeps the failures.</p><pre class="mini">$ spatial bench all</pre></div>
</div>
</div></section>

<section><div class="wrap split">
<div>
<p class="eyebrow">SPATIAL Q</p>
<h2>A language for hybrid workflows.</h2>
<p class="lead">Classical, distributed and quantum in one program. The orchestrator picks a backend from a resource estimate, and refuses when a circuit does not fit or no QPU is connected. No quantum speed-up is claimed: everything is simulated.</p>
<a class="btn ghost" href="docs/spatialq.html">Specification</a>
</div>
<div class="term"><div class="bar"><i></i><i></i><i></i><span style="margin-left:8px">examples/01_bell.sq</span></div><pre>{E(BELL)}

<span class="d">$ spatial q run examples/01_bell.sq</span>
<span class="g">{E(OUT["q_bell"])}</span></pre></div>
</div></section>

<section><div class="wrap">
<p class="eyebrow">Actual status</p>
<h2>What runs, what is only sketched.</h2>
<p class="lead">Each engine's status is declared in the code, and a test forbids showing one without evidence.</p>
<table><thead><tr><th>Engine</th><th>Level</th><th>Not done yet</th></tr></thead><tbody>
<tr><td>Fleet (agent + hub)</td><td><span class="tag ok">operational prototype</span></td><td>Several real machines, scale, hub persistence, dashboard</td></tr>
<tr><td>Compute Engine</td><td><span class="tag ok">operational prototype</span></td><td>Second real machine, NVIDIA GPU, energy measurement</td></tr>
<tr><td>Tiered memory</td><td><span class="tag ok">operational prototype</span></td><td>Kernel paging, multiple writers, RDMA/CXL</td></tr>
<tr><td>Runtime Engine</td><td><span class="tag ok">operational prototype</span></td><td>Containers, remote GUI, graphical Windows apps</td></tr>
<tr><td>SPATIAL Q</td><td><span class="tag ok">operational prototype</span></td><td>Real QPU, QIR, sub-kernels</td></tr>
<tr><td>AI</td><td><span class="tag part">first components</span></td><td>Toy model only: no real LLM, no GPU</td></tr>
<tr><td>Scientific, Simulation, Intelligence</td><td><span class="tag part">first components</span></td><td>Domain solvers, multiphysics, learned models</td></tr>
<tr><td>Holographic</td><td><span class="tag part">first components</span></td><td>Numerical optics only: no display hardware</td></tr>
</tbody></table>
</div></section>

<section><div class="wrap split">
<div class="never"><h3 style="font-size:32px;margin-bottom:12px">What Spatial Computing does not do</h3><ul>
<li>It does not add RAM. Compressed, on-disk or remote memory is typed <code>far_memory</code>, never <code>ram</code>.</li>
<li>It does not confuse virtualization with extra resources.</li>
<li>It does not claim a QPU speeds everything up: the <code>qpu</code> backend refuses to run until a provider is configured.</li>
<li>It never exposes your machine: servers listen on 127.0.0.1 and refuse any other address without explicit consent.</li>
</ul></div>
<div>
<p class="eyebrow">Open core</p>
<h2>The core is open.</h2>
<p class="lead">The CLI, audit, SPATIAL Q, runtime and tiered-memory library are published under Apache-2.0. Advanced placement and cost policies are developed in a private package, outside this repository.</p>
<a class="btn" href="docs/index.html">Read the documentation</a> <a class="btn ghost" href="{REPO}" rel="noopener">GitHub</a>
</div>
</div></section>
</main>
<footer><div class="wrap"><span>Spatial Computing · v0.9.0 · Apache-2.0</span><span>Measured on 14 November 2026 · 2017 MacBook Pro (i7-7660U, 2 cores, 16 GB)</span></div></footer>
<script src="{S.CFG["prefix"]}assets/app.js"></script></body></html>''')
    CFG["out"].mkdir(parents=True, exist_ok=True)
    (CFG["out"] / "index.html").write_text("".join(p))


def docs():
    doc("index", "Documentation", "Spatial Computing measures, compares and chooses how a workload runs. Here is where to start.",
        '''<div class="paths">
<a href="quickstart.html"><b>Install</b><span>Venv, dependencies, first command in three minutes.</span></a>
<a href="compute.html"><b>Compute Engine</b><span>Detect, monitor, compare strategies, offload.</span></a>
<a href="memory.html"><b>Tiered memory</b><span>Hot, compressed, far: a priced trade-off, not RAM.</span></a>
<a href="runtime.html"><b>Runtime Engine</b><span>Inspect a binary, pick a route, run it isolated.</span></a>
<a href="spatialq.html"><b>SPATIAL Q</b><span>Language, compiler, OpenQASM 3, backends.</span></a>
<a href="results.html"><b>Results</b><span>Every measured number and its conditions.</span></a>
</div>
<div class="callout"><b>Status</b>Version 0.9.0. Four engines are operational and tested (101 tests) on a single Mac and in CI on Linux. Nothing has been proven on a second machine, a data-center GPU or a QPU. See <a href="limits.html">Limitations</a>.</div>
<h2>Principles</h2>
<ul><li><b>A measurement before any claim.</b> Every run produces a <code>Measurement</code>; failures are kept.</li>
<li><b>Verified result.</b> A faster strategy is kept only if it computes the same thing as the reference.</li>
<li><b>Explicit refusals.</b> What a machine cannot do is stated with the reason, never faked.</li>
<li><b>No implicit network exposure.</b> Everything listens on loopback by default.</li></ul>''',
        [("First command", f'<span class="k">$ spatial audit</span>\n<span class="d">{out_block("audit", 7)}</span>')])

    doc("quickstart", "Installation", "Python 3.10 or newer. Tested on macOS 13 (Intel) with Python 3.13, and in CI on Linux and macOS.",
        f'''<div class="callout"><b>On PyPI</b>Published as <code>spatial-computing</code>. To work on the code itself, clone the GitHub repository and run <code>pip install -e ".[quantum,dev]"</code>.</div>
<h2>1. Environment</h2>
<pre id="q1"><code>{E(INSTALL.splitlines()[0])}
{E(INSTALL.splitlines()[1])}</code></pre>
<p>The <code>quantum</code> extra adds Qiskit, Qiskit Aer and the OpenQASM 3 importer. Without it SPATIAL Q works with its built-in simulator but not with the <code>aer</code> backend.</p>
<p><code>numpy</code> (&lt; 2.2) and <code>numba</code> (&lt; 0.62) are bounded: newer Numba needs an <code>llvmlite</code> that does not build on the reference Mac.</p>
<h2>2. Verify</h2>
<pre><code>spatial audit
spatial status
pytest</code></pre>
<h2>3. Linux micro-VM (optional)</h2>
<p>The <code>microvm</code> route of the Runtime Engine needs QEMU (for example <code>sudo port install qemu</code> with MacPorts) and two files downloaded once into <code>vendor/</code>, checked by SHA-256.</p>
<pre><code>mkdir -p vendor &amp;&amp; cd vendor
curl -O https://dl-cdn.alpinelinux.org/alpine/v3.22/releases/x86_64/netboot/vmlinuz-virt
curl -o busybox-x86_64 https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox
shasum -a 256 -c SHA256SUMS</code></pre>
<h2>4. Test binaries (optional)</h2>
<p>To reproduce the runtime tests, install the <code>build</code> extra (the <code>ziglang</code> cross-compiler) and run <code>spatial bench runtime</code>: it compiles the same C program for macOS, Linux, Windows and WASM into <code>benchmarks/build/</code>.</p>''',
        [("Verification", '<span class="k">$ spatial status</span>\n<span class="d">Spatial Compute Engine          operational-prototype\nSpatial Resource Engine         operational-prototype\nSpatial Runtime Engine          operational-prototype\nSPATIAL Q                       operational-prototype\n…</span>'),
         ("Tests", '<span class="k">$ pytest</span>\n<span class="g">68 passed, 9 skipped</span>\n<span class="d"># the skipped ones need benchmarks/build, QEMU or Wine</span>')])

    doc("fleet", "Fleet", "An agent on every machine, a hub that sees the whole fleet: measure, place, recommend, audit.",
        f'''<div class="callout warn"><b>Scope</b>Validated with up to 3 agents on <b>one</b> machine. The three report the same CPU load, so this proves the chain (identity, scopes, placement, results, audit), not scaling.</div>
<h2>The parts</h2>
<ul><li><b>Agent</b> (<code>spatial agent</code>): measures CPU, RAM, memory pressure and NVIDIA GPUs every few seconds, reports to the hub, asks for work and runs it. Outbound connections only. Buffers measurements while the hub is down and delivers them with their original times.</li>
<li><b>Hub</b> (<code>spatial serve hub</code>): keeps each node's measurements, queues and places tasks, computes utilization and recommendations. It never changes a machine by itself.</li>
<li><b>Operator CLI</b> (<code>spatial fleet</code>): status, recommendations, submit, result.</li></ul>
<h2>Run it</h2>
<pre><code>{E(RUN_FLEET)}</code></pre>
<h2>Placement</h2>
<p>Pull-based. An agent asks for work and receives the best queued task it is eligible for: priority first, then arrival order. Tasks can require a GPU, a minimum of free RAM, a label or a pinned node. A node at 90 % CPU or more receives nothing. Every placement is recorded, with its reason, in a hash-chained decision log. Agents run only allow-listed workloads by name: no code travels to an agent.</p>
<h2>Recommendations</h2>
<table><thead><tr><th>Kind</th><th>Triggered by</th></tr></thead><tbody>
<tr><td><code>node_down</code></td><td>No report for 30 s</td></tr>
<tr><td><code>memory_pressure</code></td><td>Less than 10 % RAM free</td></tr>
<tr><td><code>gpu_underused</code></td><td>GPUs below 20 % on average</td></tr>
<tr><td><code>rebalance</code></td><td>A node at 80 % or more next to a node at 15 % or less</td></tr>
<tr><td><code>consolidate</code></td><td>The fleet's busy cores would fit on fewer nodes at a 60 % target, RAM checked at 85 %</td></tr></tbody></table>
<p>Each one shows its evidence and its assumptions. A saving in dollars appears only if you gave the machine's price (<code>--usd-per-hour</code>), and it is an <b>estimate</b>: it becomes a result only when you apply the change and measure the fleet again.</p>
<h2>Security</h2>
<p>Encrypted, forward-secret transport. With scoped credentials, a node's identity is its credential name: an agent cannot report as another node, cannot read the fleet and cannot submit tasks; a reader cannot inject measurements. Quotas, expiry, revocation and an audit log apply. Not independently reviewed.</p>
<h2>Limits</h2>
<p>Single-process hub with in-memory state (no persistence, no high availability), no dashboard UI, heuristic recommendations, placement that does not move running work. Full description: <code>docs/INFRASTRUCTURE.md</code>.</p>''',
        [("Measured: 12 tasks, 1 agent versus 3", '<span class="d">1 agent     7.2 s\n3 agents    4.3 s  (x1.66)\nresults identical to the reference: 12 / 12\nplacement: 6, 4, 2 tasks\n(one 2-core machine: speed-up is bounded)</span>'),
         ("spatial fleet status", f'<span class="d">{E(FLEET_STATUS)}</span>')])

    doc("compute", "Compute Engine", "Detects the hardware, measures its usage, compares execution strategies and picks the best one.",
        '''<h2>Detect and monitor</h2>
<p><code>spatial audit</code> reads the real hardware (model, cores, SIMD instruction set, GPU, RAM, swap, storage) and the current state: memory pressure, macOS compressor ratio, idle resources, then lists the limits that follow.</p>
<h2>Compare strategies</h2>
<p>The <code>ComputeScheduler</code> runs each strategy on a reference computation, measures duration, CPU time and peak memory, and <b>rejects any result that differs from the reference</b>. Strategies for the demo workload: pure Python, NumPy, Numba JIT, Numba multi-thread, cold and warm process pool, remote worker, local + worker distributed.</p>
<pre><code>from spatial.compute import detect_node
from spatial.compute.scheduler import ComputeScheduler

sched = ComputeScheduler(detect_node())
rows = sched.compare("exp", {"n": 4000, "iters": 300}, sched.mandel_strategies())
best = sched.choose(rows, objective="time")   # "time" | "cpu" | "energy"</code></pre>
<h2>Offload to a worker</h2>
<p>The worker only runs named workloads from an allow-list: no code is transmitted. It listens on 127.0.0.1 and requires a token (HMAC).</p>
<pre><code>python3 -c "import os;open('token','wb').write(os.urandom(32))" &amp;&amp; chmod 600 token
spatial serve compute --token-file token</code></pre>
<div class="callout warn"><b>Note</b>A worker started on the same machine measures protocol cost, not the benefit of a second machine. That benefit has not been measured yet.</div>
<h2>Costs</h2>
<p><code>CostModel</code> estimates local cost (electricity, amortization) and cloud cost (billed hour, minimum billing, egress). Every cloud line is labelled <code>estimated=True</code>: prices are unverified list values and cloud speed is assumed.</p>
<div class="callout"><b>Energy</b>The Mac's battery gauge stayed frozen at 32.5 W between idle and full load: per-run energy cannot be measured with it. It needs <code>powermetrics</code> (administrator) or a power meter.</div>''',
        [("Measured result (n = 700)", '<span class="d">Pure Python          3.91 s\nNumPy                1.13 s\nNumba JIT            0.124 s   ×31.6\nNumba 2 cores        0.061 s   ×64.5\nCold process pool    1.11 s\nWarm process pool    0.067 s</span>'),
         ("Audit", f'<span class="k">$ spatial audit</span>\n<span class="d">{out_block("audit", 8)}</span>')])

    doc("memory", "Tiered memory", "Address more data than the local RAM budget, trading RAM for CPU and latency.",
        '''<div class="callout warn"><b>This is not RAM</b>The compressed tier costs CPU. The far tier costs latency. The <code>far_memory</code> type is distinct from <code>ram</code> throughout the code, and a test enforces it.</div>
<h2>The three tiers</h2>
<table><thead><tr><th>Tier</th><th>Content</th><th>Cost</th></tr></thead><tbody>
<tr><td>Hot</td><td>Uncompressed pages in RAM, LRU</td><td>None</td></tr>
<tr><td>Compressed</td><td>Compressed (LZ4 or zlib-1) and deduplicated pages in RAM</td><td>Compression CPU</td></tr>
<tr><td>Far</td><td>File on SSD or a remote page server</td><td>Access latency</td></tr></tbody></table>
<h2>Usage</h2>
<pre><code>from spatial.memory import TieredStore, FileBackend

st = TieredStore(hot_bytes=16 &lt;&lt; 20, compressed_bytes=16 &lt;&lt; 20,
                 far=FileBackend("/tmp/far.bin"),
                 prefetch=16, keep_far_copy=True)
st.put(0, page_bytes)
st.get(0)
print(st.stats())</code></pre>
<p><code>stats()</code> always separates logical bytes from bytes actually held in local RAM, and gives per-tier hit ratio and latency (mean or p50/p99).</p>
<h2>Measured optimizations</h2>
<ul><li><b>Read-ahead</b> on sequential-scan detection.</li><li><b>Keeping the far copy</b> of an unmodified page: its next eviction costs no write.</li></ul>
<p>On an emulated 0.2 ms link, a sequential scan goes from 2,605 to 2,047 µs per access with read-ahead, then to 1,305 µs with the far copy kept.</p>
<h2>Limits</h2>
<p>A Python library used through an API: not transparent kernel paging, and macOS offers none in user space. Single writer, no encryption or replication of far pages. The LAN and WAN links in the benchmarks are <b>emulated</b>.</p>''',
        [("Real example (16 MB logical)", f'<span class="d">{out_block("mem")}</span>'),
         ("Measured: 134 MB of data, skewed access", '<span class="d">all in RAM       0.76 µs/access   134 MB RAM\ntiers + SSD      80.5 µs/access    33.5 MB RAM\n20 ms emulated   13,957 µs/access  8.4 MB RAM\n link            (33.6 MB dataset)</span>')])

    doc("runtime", "Runtime Engine", "Inspects a binary, lists the possible execution routes with the reason for every refusal, and runs the first feasible one.",
        '''<h2>Inspect and plan</h2>
<p><code>spatial plan</code> identifies the format (Mach-O, ELF, PE, WASM, script), the target system and architecture from the headers, then lists the routes. A route is marked feasible only if its prerequisites were detected on the machine.</p>
<h2>Run</h2>
<p><code>spatial run</code> takes the first feasible route (or the one given with <code>--route</code>) and returns the program's output.</p>
<table><thead><tr><th>Route</th><th>Use</th><th>Isolation</th></tr></thead><tbody>
<tr><td><code>native</code></td><td>Same system and same CPU</td><td>None</td></tr>
<tr><td><code>microvm-hvf</code></td><td>Linux x86_64 ELF on an x86_64 host</td><td>Hardware VM, no network, no disk</td></tr>
<tr><td><code>microvm-tcg</code></td><td>Other CPU, software emulation</td><td>Emulated VM</td></tr>
<tr><td><code>wasm-node-wasi</code></td><td>WASM modules</td><td>WASI sandbox</td></tr>
<tr><td><code>wine</code></td><td>Windows binaries (console program tested)</td><td>Host process (weak)</td></tr></tbody></table>
<div class="callout warn"><b>Windows</b>With Wine present, a Windows console binary runs and returns the reference checksum. Without Wine the engine says so instead of pretending. Wine is never installed automatically (third-party build, user consent required). Graphical applications are untested.</div>
<h2>Measured on one C program</h2>
<table><thead><tr><th>Route</th><th>Compute</th><th>Startup</th></tr></thead><tbody>
<tr><td>native</td><td>1.00×</td><td>0.005 s</td></tr>
<tr><td>WASM / WASI</td><td>1.48×</td><td>0.07 s</td></tr>
<tr><td>micro-VM HVF</td><td>1.04×</td><td>0.88 s</td></tr>
<tr><td>micro-VM TCG (emulation)</td><td>23.8×</td><td>3.4 s</td></tr>
<tr><td>Windows .exe under Wine</td><td>1.35 to 1.59×</td><td>about 4.5 s</td></tr></tbody></table>
<p>Comparison with Docker Desktop, UTM, Parallels or CrossOver: not done, none is installed here.</p>''',
        [("Windows binary", f'<span class="k">$ spatial plan bench-windows.exe</span>\n<span class="d">{out_block("plan_exe")}</span>'),
         ("Linux ELF", f'<span class="k">$ spatial plan bench-linux.elf</span>\n<span class="d">{out_block("plan_elf")}</span>\n\n<span class="k">$ spatial run bench-linux.elf 300 200</span>\n<span class="g">{out_block("run_elf")}</span>')])

    doc("spatialq", "SPATIAL Q", "A hybrid workflow language: classical, distributed and quantum, with backend choice from a resource estimate.",
        '''<div class="callout"><b>Honesty</b>Everything that runs is <b>classical simulation</b>. No QPU is connected and no quantum speed-up is measured.</div>
<h2>A program</h2>
<pre><code>quantum bell() {
    qubit q[2];
    h q[0];
    cx q[0], q[1];
}

task heavy(n: int) on any {
    return workload("mandel_numba", n = n, iters = 200);
}

main {
    let counts = sample bell() shots 2000;
    print counts, expect "ZZ" of bell();
}</code></pre>
<h2>Kernels, tasks, main</h2>
<ul><li><code>quantum</code>: a circuit specialized for its arguments at call time. Classical loops and <code>if</code> are evaluated at compile time; <code>measure</code> and feed-forward (<code>if m { x q[2]; }</code>) give dynamic circuits.</li>
<li>Kernels can call sub-kernels that take qubit parameters: <code>quantum entangle(a: qubit, b: qubit) { h a; cx a, b; }</code>.</li>
<li><code>task … on cpu|worker|any</code>: classical work, local or offloaded.</li>
<li><code>main</code>: orchestration; <code>parallel { … }</code> runs branches simultaneously.</li></ul>
<h2>Gates</h2>
<p><code>h x y z s sdg t tdg sx</code> · <code>rx ry rz p</code> · <code>cx cz swap cp crz</code> · <code>ccx</code>. Bit strings follow Qiskit's convention (qubit 0 on the right).</p>
<h2>Compilation chain</h2>
<p>Source → AST → SQIR circuit (JSON intermediate representation) → optimizer (inverse-pair cancellation, rotation merging) → backend, or <b>OpenQASM 3</b> export.</p>
<table><thead><tr><th>Backend</th><th>State</th></tr></thead><tbody>
<tr><td><code>statevector</code></td><td>Built-in exact NumPy simulator</td></tr>
<tr><td><code>aer</code></td><td>Qiskit Aer (<code>quantum</code> extra)</td></tr>
<tr><td><code>qasm3</code></td><td>OpenQASM 3 export, reloaded successfully by Qiskit in a test</td></tr>
<tr><td><code>qir</code></td><td>QIR base-profile export for static circuits, validated with pyqir</td></tr>
<tr><td><code>qpu</code></td><td>IBM Quantum through <code>qiskit-ibm-runtime</code> (<code>qpu</code> extra). Needs a token and an instance; otherwise refuses with the reason, no silent fallback. A Bell pair has run on ibm_marrakesh: 90 % correlated outcomes, the rest hardware noise.</td></tr></tbody></table>
<h2>Orchestrator refusals</h2>
<p>A circuit whose state vector (16 × 2<sup>n</sup> bytes) exceeds half of the available RAM is refused with an explicit message. On the reference Mac: about 27 qubits.</p>
<p>The full grammar is in <code>docs/06_SPATIAL_Q_SPEC.md</code>.</p>''',
        [("Run", f'<span class="k">$ spatial q run examples/01_bell.sq --seed 1</span>\n<span class="g">{out_block("q_bell")}</span>'),
         ("Export to OpenQASM 3", f'<span class="k">$ spatial q qasm examples/04_teleport.sq --args \'[1.0]\'</span>\n<span class="d">{out_block("q_qasm")}</span>'),
         ("Hybrid loop (VQE)", f'<span class="k">$ spatial q run examples/03_vqe_hybrid.sq</span>\n<span class="g">{out_block("q_vqe")}</span>\n<span class="d"># exact energy: -1.851199124123644</span>')])

    doc("cli", "Commands", "Every command of the <code>spatial</code> command line.",
        '''<table><thead><tr><th>Command</th><th>Role</th></tr></thead><tbody>
<tr><td><code>spatial audit [--json]</code></td><td>Hardware, current usage, limits of this machine</td></tr>
<tr><td><code>spatial status</code></td><td>Real status of every engine and what is not done</td></tr>
<tr><td><code>spatial plan &lt;file&gt;</code></td><td>Detected format and execution routes, with reasons</td></tr>
<tr><td><code>spatial run &lt;file&gt; [args] [--route R] [--timeout S]</code></td><td>Runs via the first feasible route; exit code 1 if impossible</td></tr>
<tr><td><code>spatial q run|check|qasm|qasm2|qir|ir &lt;file.sq&gt; [--noise p] [--compiled]</code></td><td>Run (optionally with depolarising noise), check, export to OpenQASM 3, OpenQASM 2, QIR or SQIR</td></tr>
<tr><td><code>spatial bench cpu|memory|gpu|runtime|q|all</code></td><td>Redo the measurements and regenerate the results table</td></tr>
<tr><td><code>spatial serve compute|memory|runtime --token-file F | --master-key-file F</code></td><td>Start a worker, a page server or a sandboxed binary runner, on loopback; with a master key, tenants get scoped credentials</td></tr>
<tr><td><code>spatial agent --hub H:P --token-file F [--usd-per-hour X]</code></td><td>Run a fleet agent: measure this machine, report to a hub, run allow-listed tasks</td></tr>
<tr><td><code>spatial fleet status|advise|submit|result --hub H:P --token-file F</code></td><td>See the fleet, get recommendations with their evidence, submit and read tasks</td></tr>
<tr><td><code>spatial serve hub --master-key-file F</code></td><td>Start the fleet hub</td></tr>
<tr><td><code>spatial token init|issue --master-key-file F [--name N --scopes S --ttl T --max-ops N --max-bytes B]</code></td><td>Create a master key; issue a scoped, expiring, quota-limited credential</td></tr></tbody></table>
<p>An error prints a single <code>spatial: Type: message</code> line and exits with code 1.</p>''',
        [("Clean error", f'<span class="k">$ spatial run /nonexistent</span>\n<span class="d">{out_block("unknown")}</span>'),
         ("Check a program", f'<span class="k">$ spatial q check examples/05_ghz_qft.sq</span>\n<span class="g">{out_block("q_qpu")}</span>')])

    doc("security", "Security", "What the prototype protects, and what it does not protect yet.",
        '''<h2>In place</h2>
<ul><li><b>Loopback by default.</b> Binding another address raises <code>PermissionError</code> unless <code>--allow-remote</code> is passed: an explicit act by the machine's owner.</li>
<li><b>Authentication.</b> A random 32-byte token (file mode 600) and an HMAC-SHA256 challenge-response; a wrong token is dropped without a reply.</li>
<li><b>No code transmitted.</b> The worker only runs named workloads from an allow-list.</li>
<li><b>Closed micro-VM.</b> No network device, no disk, no host folder; RAM capped.</li>
<li><b>Quota</b> on the page server's memory.</li>
<li><b>Encrypted, forward-secret channel.</b> Every record is sealed with AES-256-GCM; keys come from an ephemeral X25519 exchange mixed with the secret, so a recorded session stays unreadable if the secret leaks later. A modified or replayed record is rejected.</li>
<li><b>Scoped permissions.</b> A server started with a master key issues credentials with scopes (<code>run:mandel_numba</code>, <code>mem:read</code>, <code>exec:elf</code>), an expiry and quotas; every request, allowed or denied, goes to the audit log.</li>
<li><b>Encrypted and replicated far pages</b> with <code>EncryptedBackend</code> and <code>ReplicatedBackend</code>.</li>
<li><b>Tamper-evident ledger.</b> Measurements are hash-chained; <code>Ledger.verify()</code> finds an edited row.</li></ul>
<h2>Not in place yet</h2>
<ul><li>An independent security review. None has been done.</li>
<li>Certificate-based identity (the secret is the identity), a <i>signed</i> audit log, revocation and usage counters that survive a restart.</li>
<li>A sandbox for arbitrary third-party workloads.</li></ul>
<div class="callout warn"><b>Do not expose</b>Do not use <code>--allow-remote</code> on a network you do not control: the protocol has had no independent review.</div>
<p>To report a vulnerability, use GitHub's private vulnerability reporting on the repository.</p>''',
        [("Refusal of a public address", '<span class="d">RpcServer(handler, token, host="0.0.0.0")\n→ PermissionError: refusing to bind a\n  non-loopback address without\n  allow_remote=True (explicit user\n  consent required to expose this machine)</span>')])

    doc("results", "Results", "Figures measured on 14 November 2026 on a 2017 MacBook Pro (Intel i7-7660U, 2 cores, 16 GB, macOS 13.7.8), on AC power.",
        '''<div class="callout warn"><b>Conditions</b>A single machine, 1 to 5 repetitions, no confidence interval. On a low battery the same tests were about three times slower: the processor is throttled.</div>
<table><thead><tr><th>Test</th><th>Result</th></tr></thead><tbody>
<tr><td>CPU, n = 700</td><td>Pure Python 3.91 s · Numba 0.124 s (×31.6) · Numba 2 cores 0.061 s (×64.5)</td></tr>
<tr><td>CPU, n = 4000</td><td>1 thread 4.18 s · 2 cores 2.05 s (×2.04)</td></tr>
<tr><td>Integrated GPU (Metal, float32)</td><td>20 to 33× the two cores, against a non-vectorized CPU reference</td></tr>
<tr><td>System memory</td><td>macOS holds 7.3 GiB of pages in 2.1 GiB (ratio 3.4)</td></tr>
<tr><td>Tiers + SSD</td><td>33.5 MB of local RAM for 134 MB; 80.5 µs/access against 0.76 µs</td></tr>
<tr><td>Dataset larger than RAM</td><td>24 GiB through a 512 MiB budget on a 16 GiB Mac: 0 corrupt pages in 2,648 verified, process RSS peak 578 MiB, about 5 ms per random access (disk-backed, one run)</td></tr>
<tr><td>Linux micro-VM (HVF)</td><td>0.88 s startup; compute at 1.04× native</td></tr>
<tr><td>SPATIAL Q</td><td>Fidelity 1.000 against Qiskit up to 16 qubits; VQE reaches the exact energy</td></tr>
<tr><td>SPATIAL Q on real hardware</td><td>5 circuits on ibm_marrakesh; the simulator with asymmetric readout error halves the gap to the device (one shared parameter set)</td></tr></tbody></table>
<h2>Reproduce</h2>
<pre><code>spatial bench all</code></pre>
<p>The full table, with the cost assumptions, is generated in <code>docs/RESULTATS.fr.md</code> (French). Costs are estimates: no cloud resource was rented and energy could not be measured.</p>''',
        [("Reproduce", '<span class="k">$ spatial bench cpu</span>\n<span class="k">$ spatial bench memory</span>\n<span class="k">$ spatial bench runtime</span>\n<span class="k">$ spatial bench q</span>\n<span class="d"># writes benchmarks/results/*.json\n# then docs/RESULTATS.fr.md</span>')])

    doc("limits", "Limitations", "What is missing, said plainly.",
        '''<table><thead><tr><th>Limit</th><th>Consequence</th></tr></thead><tbody>
<tr><td>A single machine</td><td>Offload and remote memory validated over loopback or an emulated link; no capacity gain demonstrated</td></tr>
<tr><td>2 cores, integrated GPU without float64</td><td>Parallelism bounded near 2×; no model inference</td></tr>
<tr><td>No CXL, RDMA, NPU, QPU</td><td>Studied on paper only</td></tr>
<tr><td>Energy not measurable</td><td>Energy costs are estimated</td></tr>
<tr><td>Windows</td><td>One console program run under Wine; graphical apps untested</td></tr>
<tr><td>Protocol not independently reviewed; no certificates</td><td>Do not expose to an untrusted network</td></tr>
<tr><td>Exact quantum simulation</td><td>About 27 qubits here, bounded by RAM</td></tr>
<tr><td>AI, scientific, simulation, intelligence, holographic domains</td><td>First components only (toy model, small solvers, numerical optics)</td></tr></tbody></table>
<p>The detailed, current list is in <code>docs/LIMITATIONS.md</code>; every test not yet done, with how to run it, is in <code>docs/TESTS_NOT_DONE.md</code>; open work is in <code>ROADMAP.md</code>.</p>''',
        [("Engine status", '<span class="k">$ spatial status</span>\n<span class="d">compute / memory / runtime / SPATIAL Q\n  operational-prototype\nAI / scientific / simulation /\nintelligence / holographic\n  first-components</span>')])

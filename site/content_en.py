"""English content for the site (served at the root). Scaffolding lives in scaffold.py."""
from scaffold import CFG, E, OUT, REPO, ROOT, alt_url, doc, head, nav, out_block
import scaffold as S
import pages_new
import pages_console

NAV_GROUPS = [
    ("Get started", [("index", "Overview"), ("quickstart", "Quickstart")]),
    ("Console", [("console", "Console and accounts"), ("api", "REST API")]),
    ("Engines", [("planner", "Planner"), ("fleet", "Fleet"), ("compute", "Compute Engine"), ("memory", "Tiered memory"), ("runtime", "Runtime Engine"), ("spatialq", "SPATIAL Q"), ("accelerators", "Accelerators"), ("interconnect", "Interconnect")]),
    ("Operate", [("operations", "Operations")]),
    ("Reference", [("cli", "Commands"), ("security", "Security"), ("results", "Results"), ("limits", "Limitations"), ("roadmap", "Roadmap"), ("changelog", "Changelog")]),
]
UI = {"nav_label": "Main", "proof": "Proof", "install": "Install", "docs_label": "Documentation", "examples_label": "Examples"}

INSTALL = """python3 -m venv .venv && source .venv/bin/activate
pip install "spatial-computing[quantum]"
spatial audit
spatial status"""

RUN_FLEET = 'spatial token init --master-key-file hub.key\nspatial serve hub --master-key-file hub.key --port 7700\nspatial token issue --master-key-file hub.key --name node-1 --scopes fleet:report,fleet:work > node-1.tok\nspatial token issue --master-key-file hub.key --name ops --scopes fleet:read,fleet:submit > ops.tok\n# on every machine\nspatial agent --hub HUB:7700 --token-file node-1.tok --usd-per-hour 1.5\n# the operator\nspatial fleet status --hub HUB:7700 --token-file ops.tok\nspatial fleet advise --hub HUB:7700 --token-file ops.tok\nspatial fleet submit --hub HUB:7700 --token-file ops.tok --workload mandel_numba --params \'{"n":1400,"iters":300}\''
FLEET_STATUS = 'node     up  cores cpu% ramfree%\nagent-0  yes     4   48       43\nagent-1  yes     4   50       43\nagent-2  yes     4   52       43\nfleet: 3 nodes, 12 cores,\nCPU utilization 50.1%\n(last 6 s)'

PLAN_CMDS = 'spatial optimize compute --family heat --params \'{"n":100,"steps":600}\' --execute\nspatial optimize dataset --gib 24 --accesses 200000 --max-ram-gib 2\nspatial optimize kv --prefix-tokens 2000 --reuse 0.8 --execute\nspatial optimize quantum --file examples/01_bell.sq --kernel bell --shots 1000\nspatial optimize binary --file app.elf --isolated 64 50'
PLAN_HEAT = "job: compute heat {'n': 100, 'steps': 600}\nobjective: minimize cost (0.134 $/h)\n>> compute/numba    0.0106 s   chosen\n   compute/numpy    0.0733 s   ok\nexecuted: 0.0114 s (estimated 0.0106 s, +8%)"
PLAN_DATA = 'job: dataset 24 GiB, 200000 accesses\nobjective: minimize cost, RAM <= 2 GiB\n>> memory/tiered_ssd  41.4 s   chosen\n   memory/in_ram      -        rejected: 24.0 GiB does\n                      not fit the 2.0 GiB RAM budget'

BELL = open(ROOT.parent / "examples/01_bell.sq").read().strip()


def landing():
    import landing_new
    from spatial import __version__
    landing_new.render("en", {"INSTALL": INSTALL, "PLAN": PLAN_HEAT, "FLEET": FLEET_STATUS, "BELL": BELL, "Q_OUT": OUT["q_bell"]}, __version__)


def docs():
    doc("index", "Documentation", "Spatial Computing measures, compares and chooses how a workload runs. Here is where to start.",
        '''<div class="paths">
<a href="console.html"><b>Console</b><span>Create an account, an app, an API key; send jobs; watch usage and pay.</span></a>
<a href="quickstart.html"><b>Quickstart</b><span>From zero to a first job, with the console or the CLI.</span></a>
<a href="api.html"><b>REST API</b><span>Everything the console does, for scripts.</span></a>
<a href="compute.html"><b>Compute Engine</b><span>Detect, monitor, compare strategies, offload.</span></a>
<a href="memory.html"><b>Tiered memory</b><span>Hot, compressed, far: a priced trade-off, not RAM.</span></a>
<a href="runtime.html"><b>Runtime Engine</b><span>Inspect a binary, pick a route, run it isolated.</span></a>
<a href="spatialq.html"><b>SPATIAL Q</b><span>Language, compiler, OpenQASM 3, backends.</span></a>
<a href="accelerators.html"><b>Accelerators and kernels</b><span>One job on CPU, Metal, NVIDIA or AMD; kernels written once.</span></a>
<a href="interconnect.html"><b>Interconnect</b><span>Encrypted collectives with a measured cost model.</span></a>
<a href="operations.html"><b>Operations</b><span>Failover, dashboard, alerts, scale.</span></a>
<a href="roadmap.html"><b>Roadmap</b><span>What is built, what needs hardware or people.</span></a>
<a href="results.html"><b>Results</b><span>Every measured number and its conditions.</span></a>
</div>
<div class="callout"><b>Status</b>Version 0.16.0. Four engines are operational and tested (178 tests) on a single Mac and in CI on Linux. Nothing has been proven on a second machine, a data-center GPU or a QPU. See <a href="limits.html">Limitations</a>.</div>
<h2>Principles</h2>
<ul><li><b>A measurement before any claim.</b> Every run produces a <code>Measurement</code>; failures are kept.</li>
<li><b>Verified result.</b> A faster strategy is kept only if it computes the same thing as the reference.</li>
<li><b>Explicit refusals.</b> What a machine cannot do is stated with the reason, never faked.</li>
<li><b>No implicit network exposure.</b> Everything listens on loopback by default.</li></ul>''',
        [("First command", f'<span class="k">$ spatial audit</span>\n<span class="d">{out_block("audit", 7)}</span>')])

    doc("quickstart", "Quickstart", "From zero to a first job. Two ways: the console (accounts, keys, jobs) or the command line alone.",
        f'''<h2>Fastest path: the console</h2>
<ol><li>Open the console (<code>http://127.0.0.1:8090</code> if you run it yourself, see <a href="console.html">Console and accounts</a>) and <b>create an account</b>.</li>
<li>On the Overview, press <b>New app</b>, then create a <b>node key</b> and a <b>client key</b> (API keys). Each is shown once: save it.</li>
<li>On a machine: <code>pip install "spatial-computing[quantum]"</code>, then <code>spatial agent --hub HUB:7700 --token-file node.tok</code>. It appears in <b>Fleet</b>.</li>
<li>Open <b>Jobs</b>, pick <code>montecarlo_pi</code>, submit. See the result, the usage and the estimated charge in <b>Usage &amp; billing</b>.</li></ol>
<p>Prefer scripts? The same steps are in the <a href="api.html">REST API</a>.</p>
<h2>Command line only</h2>
<div class="callout"><b>Python 3.10 or newer</b>Tested on macOS 13 (Intel) with Python 3.13, and in CI on Linux and macOS.</div>
<div class="callout"><b>On PyPI</b>Published as <code>spatial-computing</code>. To work on the code itself, clone the GitHub repository and run <code>pip install -e ".[quantum,dev]"</code>.</div>
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
         ("Tests", '<span class="k">$ pytest</span>\n<span class="g">196 passed, 1 skipped</span>\n<span class="d"># the skipped one needs a tool that is not installed</span>')])

    doc("planner", "Planner", "One objective for every engine: get each job done correctly at the lowest cost, and prove it.",
        f'''<div class="callout"><b>The objective</b>Get the job done <b>correctly</b> at the lowest <b>cost in dollars</b>, within the constraints you state (deadline, RAM, isolation, hardware allowed), and <b>prove it</b>: the estimate is recorded next to what really happened, and future estimates are corrected by that history.</div>
<h2>How the engines fit together</h2>
<p>Each engine has a provider that turns a job into priced options. One function ranks them. One ledger records the decision and, after execution, the measurement.</p>
<table><thead><tr><th>Engine</th><th>Options it proposes</th></tr></thead><tbody>
<tr><td>Compute, Simulation, Scientific, Holographic</td><td>Each variant of a numerical job (e.g. pure Python, NumPy, Numba, multi-core), probed on reduced problems and checked against the others</td></tr>
<tr><td>Fleet</td><td>The same job on each live node, at the node's own price per hour</td></tr>
<tr><td>Accelerator fabric</td><td>The same job on the CPU, a Metal GPU or an NVIDIA GPU (the NVIDIA path is written, never run on real hardware); on the reference Mac the planner picked the faster device in 7 of 7 sizes</td></tr>
<tr><td>Portable kernels</td><td>One kernel source, run on the CPU or a Metal GPU (CUDA C is generated, never run); the integer kernel is bit-identical on both; device choice right in 4 of 6 cases, misses at the crossover</td></tr>
<tr><td>Virtual interconnect</td><td>Encrypted all-reduce between workers (ring, halving-doubling, tree), algorithm chosen by a measured cost model; on one machine it is about 3,000 times below NVLink 5 on bandwidth, so it is a software layer, not a replacement</td></tr>
<tr><td>Tiered memory</td><td>A dataset in RAM or tiered over SSD, with tier latencies measured on this machine</td></tr>
<tr><td>Runtime</td><td>Every route for a binary (native, WASM, micro-VM, Wine) with its isolation and overhead</td></tr>
<tr><td>SPATIAL Q</td><td>Exact simulator, Aer, or real hardware (only if allowed and priced)</td></tr>
<tr><td>AI</td><td>A cached prefix: recompute, or keep and restore it</td></tr></tbody></table>
<h2>Use it</h2>
<pre><code>{E(PLAN_CMDS)}</code></pre>
<h2>Is the decision good?</h2>
<p>Every feasible option was run for real and timed, then compared with the planner's choice (one machine, one price per hour, so cheapest = fastest).</p>
<table><thead><tr><th>Estimator</th><th>Cases</th><th>Picked the fastest</th><th>Median estimate error</th></tr></thead><tbody>
<tr><td>Single probe</td><td>13</td><td>10 (77 %)</td><td>28 %</td></tr>
<tr><td>Two sizes, affine fit</td><td>13</td><td>10 (77 %)</td><td>16 %</td></tr>
<tr><td>+ best of several probes</td><td>13</td><td>12 (92 %)</td><td>7 %</td></tr>
<tr><td>Same, on 12 cases never used while tuning</td><td>12</td><td>12 (100 %)</td><td>5 %</td></tr></tbody></table>
<p>The first versions mis-ranked the multi-core variant on mid-size jobs because microsecond probes were dominated by thread start-up noise; keeping the best of several runs fixed it.</p>
<div class="callout warn"><b>Limits</b>One machine, 25 cases, numerical kernels and circuit simulation only. Estimates are per machine (the planner re-probes each time). Calibration is a median of past ratios, not a learned model. Dollar costs use the prices you give: the default local price (0.134 $/h) is an assumption, a fleet node without a price is rejected, and a QPU tariff is never guessed. The AI engine is a toy model. Details: <code>docs/OBJECTIVE.md</code>.</div>''',
        [("Example: compute", f'<span class="d">{E(PLAN_HEAT)}</span>'), ("Example: dataset", f'<span class="d">{E(PLAN_DATA)}</span>')])

    doc("fleet", "Fleet", "An agent on every machine, a hub that sees the whole fleet: measure, place, recommend, audit.",
        f'''<div class="callout warn"><b>Scope</b>Validated on <b>one</b> machine: up to 3 real agents, and 1,000 simulated agents (threads) against one hub. This proves the chain (identity, scopes, placement, results, audit) and the hub's limits on one box, not behaviour on a real network.</div>
<h2>The parts</h2>
<ul><li><b>Agent</b> (<code>spatial agent</code>): measures CPU, RAM, memory pressure and NVIDIA GPUs every few seconds, reports to the hub, asks for work and runs it. Outbound connections only. Buffers measurements while the hub is down and delivers them with their original times.</li>
<li><b>Hub</b> (<code>spatial serve hub</code>): keeps each node's measurements, queues and places tasks, computes utilization and recommendations. It never changes a machine by itself.</li>
<li><b>Operator CLI</b> (<code>spatial fleet</code>): status, recommendations, submit, result.</li>
<li><b>Dashboard</b> (<code>spatial dashboard</code>): a read-only page in your browser, served on 127.0.0.1 only behind a random key printed at start; nodes, alerts, recommendations, tenants, queue.</li>
<li><b>Alerts</b> (<code>spatial watch</code>, dashboard banner): edge-triggered (one event when a condition appears, one when it clears). A webhook receives them only if you pass <code>--webhook</code>; that sends fleet data off the machine.</li>
<li><b>High availability</b> (<code>--peer</code>): an active hub and a standby that copies its state; the standby promotes itself after 6 s of silence and agents follow. Measured: about 6.7 s from <code>kill -9</code> to a task finishing on the survivor. <b>Not consensus</b>: under a partition two hubs can be active until they see each other, then the lower epoch steps down and loses its divergent state. Details: <code>docs/HA.md</code>.</li></ul>
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
<p>Heuristic recommendations; placement that does not move running work; failover without a replicated log (see <a href="operations.html">Operations</a>); everything validated on one machine. Full description: <code>docs/INFRASTRUCTURE.md</code>.</p>''',
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
<tr><td><code>container</code></td><td>Static Linux ELF in Docker or Podman</td><td>Read-only root, no network, no capabilities, non-root, 256 MiB; network and a shared folder only if asked</td></tr>
<tr><td><code>desktop</code></td><td><code>spatial desktop xterm</code> (or xclock, mousepad): a graphical Linux app in a container, used from your browser through noVNC</td><td>Loopback only, one-time password, no capabilities, read-only root, 512 MiB</td></tr>
<tr><td><code>wasm-node-wasi</code></td><td>WASM modules</td><td>WASI sandbox</td></tr>
<tr><td><code>wine</code></td><td>Windows binaries (console program tested)</td><td>Host process (weak)</td></tr></tbody></table>
<div class="callout warn"><b>Windows</b>With Wine present, a Windows console binary runs and returns the reference checksum. Without Wine the engine says so instead of pretending. Wine is never installed automatically (third-party build, user consent required). A graphical window of Wine's Notepad was seen on screen; no other graphical application was tried.</div>
<h2>Measured on one C program</h2>
<table><thead><tr><th>Route</th><th>Compute</th><th>Startup</th></tr></thead><tbody>
<tr><td>native</td><td>1.00×</td><td>0.005 s</td></tr>
<tr><td>WASM / WASI</td><td>1.48×</td><td>0.07 s</td></tr>
<tr><td>micro-VM HVF</td><td>1.04×</td><td>0.88 s</td></tr>
<tr><td>micro-VM TCG (emulation)</td><td>23.8×</td><td>3.4 s</td></tr>
<tr><td>Windows .exe under Wine</td><td>1.35 to 1.59×</td><td>about 4.5 s</td></tr></tbody></table>
<p>The container route is tested with Docker through Colima (each isolation property has a test); the same tests also pass on Podman. Comparison with Docker Desktop, UTM, Parallels or CrossOver: not done.</p>''',
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
<tr><td><code>spatial optimize compute|binary|quantum|dataset|kv [--objective cost|time --deadline S --max-ram-gib G --isolated --allow-qpu --execute]</code></td><td>The one objective: price every option for a job, pick the cheapest, optionally run it and compare with the estimate</td></tr>
<tr><td><code>spatial devices</code></td><td>Compute devices the planner can use on this machine</td></tr>
<tr><td><code>spatial agent --hub H:P --token-file F [--usd-per-hour X]</code></td><td>Run a fleet agent: measure this machine, report to a hub, run allow-listed tasks</td></tr>
<tr><td><code>spatial fleet status|advise|submit|result --hub H:P --token-file F</code></td><td>See the fleet, get recommendations with their evidence, submit and read tasks</td></tr>
<tr><td><code>spatial serve hub --master-key-file F [--state-file S] [--peer H:P --name N]</code></td><td>Start the fleet hub; with a state file it survives restarts; with a peer it joins an active/standby pair</td></tr>
<tr><td><code>spatial dashboard --hub H:P --token-file F</code></td><td>Read-only fleet dashboard on 127.0.0.1, behind a random key</td></tr>
<tr><td><code>spatial watch --hub H:P --token-file F [--webhook URL]</code></td><td>Print alerts as they fire and clear</td></tr>
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

    pages_new.en()
    pages_console.render("en")

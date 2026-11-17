"""Docs pages added after the first site: accelerators and kernels, interconnect, operations (HA, dashboard,
alerts), roadmap, changelog. Same scaffold; text in English and French."""
from scaffold import CFG, E, doc

# ---------------------------------------------------------------------------------------------------- English
def en():
    doc("accelerators", "Accelerators and kernels",
        "One job, described once, placed on the cheapest device: CPU, Metal GPU, an NVIDIA GPU or a remote node. Kernels are written once and generated for each device.",
        '''<div class="callout warn"><b>Scope</b>CPU and Metal GPU are tested on one Mac. The NVIDIA (CUDA C) and AMD (HIP) sources are <b>generated, never compiled, never run</b>: this machine has neither GPU.</div>
<h2>What it is not</h2>
<ul><li><b>Not CUDA emulation.</b> NVIDIA's licence forbids translation layers that run CUDA code on other hardware. We neither translate nor reimplement CUDA. ZLUDA (Apache-2.0/MIT) was studied and not used: it needs an AMD GPU, which this machine does not have, and it solves another problem (running existing CUDA binaries elsewhere).</li>
<li><b>Not a replacement for NVIDIA's orchestration</b> (KAI/Run:ai, Dynamo): they are open source; we plug into that world instead of competing.</li></ul>
<h2>The fabric</h2>
<p>Each device runs its own native implementation of the same job. The planner probes each one on reduced sizes, checks that they agree, and picks the cheapest for the real size.</p>
<table><thead><tr><th>Device</th><th>Backend</th><th>State</th></tr></thead><tbody>
<tr><td>CPU</td><td>Numba, all cores</td><td>tested</td></tr>
<tr><td>Metal GPU</td><td>generated Metal Shading Language, compiled at run time</td><td>tested (Intel Iris Plus 640)</td></tr>
<tr><td>NVIDIA GPU</td><td>generated CUDA C / <code>numba.cuda</code></td><td><b>never run</b></td></tr>
<tr><td>AMD GPU</td><td>generated HIP source</td><td><b>never run</b></td></tr>
<tr><td>Remote node</td><td>Fleet hub</td><td>tested on loopback</td></tr></tbody></table>
<h2>Portable kernels</h2>
<p>A kernel is a typed subset of Python (<code>int</code>, <code>float32</code>, loops, branches, <code>sin</code>, <code>sqrt</code>…). The same source gives CPU code, Metal code and CUDA/HIP source. Unsupported code is refused with a line number.</p>
<pre><code>from spatial.kernel import kernel

@kernel
def collatz(i: int, j: int, n: int, limit: int):
    x = i * n + j + 1
    k = 0
    while x != 1 and k &lt; limit:
        if x % 2 == 0:
            x = x // 2
        else:
            x = 3 * x + 1
        k += 1
    return k

collatz.run("metal", 512, limit=1000)        # n x n map
collatz.reduce("metal", 512, limit=1000)     # sum over the grid, in threadgroup shared memory
print(collatz.to_cuda_c(), collatz.to_hip())</code></pre>
<h2>Measured (2017 MacBook Pro, Intel Iris Plus 640)</h2>
<table><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody>
<tr><td>Same job, CPU or Metal, device chosen by the planner</td><td>7 of 7 sizes correct; the crossover is between n = 600 and n = 1,024</td></tr>
<tr><td>Integer kernel, CPU against Metal</td><td>bit-identical, including 32-bit overflow</td></tr>
<tr><td>Float kernels</td><td>agree to float32 rounding (under 1 % of boundary pixels differ)</td></tr>
<tr><td>Reduction in shared memory, integer kernel</td><td>exact against the CPU at n = 16, 37, 100, 256</td></tr>
<tr><td>Planner choice for portable kernels</td><td>4 of 6 right, mean regret 1.09×; both misses at the crossover</td></tr></tbody></table>
<h2>Limits</h2>
<p>Two kernel shapes (2-D map, whole-grid sum). No tiling, tensor cores or other reductions. Work is modelled as n², so data-dependent kernels are only roughly proportional. Details: <code>docs/KERNELS.md</code>, <code>docs/FABRIC.md</code>.</p>''',
        [("Run it", '<span class="k">$ spatial devices</span>\n<span class="k">$ spatial optimize compute \\\n    --family pk_collatz \\\n    --params \'{"n":1536,"limit":2000}\' \\\n    --execute</span>'),
         ("Collatz, 1536 × 1536", '<span class="d">cpu         597 ms\ngpu_metal    94 ms\nplanner chose gpu_metal\n(regret 1.00×)</span>')])

    doc("interconnect", "Interconnect",
        "Collective operations between workers over the encrypted channel, with the algorithm chosen by a measured cost model.",
        '''<div class="callout warn"><b>Not an NVLink</b>NVLink is silicon and copper. This is a software layer over whatever link exists. On the reference machine its best bus bandwidth is about 0.2 to 0.3 GB/s; NVLink 5 is quoted at 900 GB/s per direction (vendor figure), about <b>3,000 to 4,000 times faster</b>.</div>
<h2>What it does</h2>
<p><code>spatial.interconnect</code> runs N processes that exchange data through SWP/2 (AES-256-GCM, forward-secret). It provides ring, halving-doubling and tree all-reduce, and broadcast. A cost model <code>t = α + M/β</code> predicts the time of each algorithm; <code>allreduce(..., algo="auto")</code> takes the cheapest.</p>
<table><thead><tr><th>Algorithm</th><th>Predicted time (M bytes, N ranks)</th><th>Good for</th></tr></thead><tbody>
<tr><td>ring</td><td>2(N−1)α + 2(N−1)/N · M/β</td><td>large messages</td></tr>
<tr><td>halving-doubling</td><td>2·log₂N·α + 2(N−1)/N · M/β (N a power of two)</td><td>medium messages</td></tr>
<tr><td>tree</td><td>2·log₂N·(α + M/β)</td><td>small messages</td></tr></tbody></table>
<h2>Measured</h2>
<ul><li>All algorithms return the exact sum (tests).</li>
<li>Fitted link on loopback: α ≈ 150 to 200 µs per message, β ≈ 650 to 740 MB/s.</li>
<li>The single shared link model chose the fastest algorithm in <b>1 of 6</b> sizes at N = 4, 8 and 16 (4 of 6 at N = 6). It always preferred halving-doubling; in practice tree won for small messages and ring for large ones.</li>
<li>Calibrating each algorithm separately fixes most of it: judged on a rank count it had not seen, 3 to 5 of 6 right, mean regret 1.07× to 1.27×. Results move from one run to the next, so read the trend, not one count.</li></ul>
<table><thead><tr><th>N = 8</th><th>ring</th><th>halving-doubling</th><th>tree</th></tr></thead><tbody>
<tr><td>1 KiB</td><td>10.4 ms</td><td>4.2 ms</td><td><b>2.0 ms</b></td></tr>
<tr><td>1 MiB</td><td>22.9 ms</td><td><b>13.8 ms</b></td><td>15.5 ms</td></tr>
<tr><td>16 MiB</td><td><b>228 ms</b></td><td>289 ms</td><td>369 ms</td></tr></tbody></table>
<h2>Limits</h2>
<p>One machine, loopback, N = 4, 6, 8, 16 as processes on two cores (this measures CPU contention as much as a link). No RDMA, no GPU memory, no fault tolerance. NCCL, MPI, UCC and MSCCL++ are mature: the value here is a cost-model-driven, encrypted, hardware-neutral layer that feeds the same planner. Details: <code>docs/INTERCONNECT.md</code>.</p>''',
        [("Use it", '<span class="d">from spatial.interconnect import launch, allreduce\n\ndef work(comm):\n    x = local_vector(comm.rank)\n    return allreduce(comm, x, algo="auto")\n\nlaunch(8, work)</span>'),
         ("Peak bus bandwidth", '<span class="d">this layer   ~0.28 GB/s\nNVLink 5    900 GB/s (vendor)\nratio       ~3,200×</span>')])

    doc("operations", "Operations",
        "Run the fleet hub for real: restarts, failover, a local dashboard, alerts. Measured on one machine; what it does not guarantee is stated.",
        f'''<h2>Dashboard</h2>
<p><code>spatial dashboard</code> opens a read-only page: nodes with CPU bars, alerts, recommendations (savings are labelled estimates), tenants and the task queue, plus the hub's role and epoch. It is served on <b>127.0.0.1 only</b> (no option to bind elsewhere), needs a random key printed at start, rejects non-loopback Host headers (DNS rebinding) and accepts GET only. For another machine, use an SSH tunnel.</p>
<p><img src="{CFG["prefix"]}../assets/dashboard.png" alt="Fleet dashboard with a node-down alert" style="max-width:100%;border:1px solid var(--line)"></p>
<h2>Alerts</h2>
<p><code>spatial watch</code> and the dashboard banner turn high-severity recommendations into events: one when a condition appears, one when it clears. <code>--webhook URL</code> POSTs them as JSON; that sends fleet data to the URL you give.</p>
<h2>Persistence and restart</h2>
<p><code>--state-file</code> saves tasks, queue and tenant usage every 5 s (atomic write). After a restart, running tasks are requeued (the workloads are pure functions, so running twice is safe) and agents reconnect by themselves. Node measurements are not saved; agents rebuild them within one report interval.</p>
<h2>High availability</h2>
<table><thead><tr><th>Mode</th><th>How</th><th>Guarantee</th></tr></thead><tbody>
<tr><td>Two hubs</td><td><code>--peer</code>: active and standby, the standby copies the state and promotes itself after 6 s</td><td>Fast failover; <b>not consensus</b>: under a partition both can be active, then the lower epoch steps down and loses its divergent state</td></tr>
<tr><td>Three or more hubs</td><td>two or more <code>--peer</code>: majority election with terms and votes, leases</td><td>At most one leader per term; a hub cut off from the majority refuses requests; state still moves by snapshots, so up to one second of changes can be lost at a failover; not a replicated log</td></tr></tbody></table>
<p>Measured on one Mac, two hub processes and one agent, <code>kill -9</code> on the active hub, 3 trials: a task submitted before the kill finished on the survivor 6.7 s later each time. Quorum mode: randomized run of 220 rounds with random crashes and restarts of 5 hubs, no term ever had two leaders (simulated clock, real loopback connections).</p>
<h2>Endurance</h2>
<p>Soak test (<code>benchmarks/soak.py</code>): a hub, 3 agents, a client submitting a task every 0.5 s with connection churn and a dashboard polling, for 15 then 12 minutes on one Mac. No errors across 1,758 and 1,419 tasks; file descriptors and threads flat. The first run showed the hub's memory growing by 12.5 MiB/h because finished tasks were kept forever; finished tasks are now capped (<code>--max-finished</code>). <b>Minutes, not days</b>: slower leaks are not ruled out.</p>
<h2>Scale</h2>
<table><thead><tr><th>Agents</th><th>Reports/s</th><th>Report p50 / p99</th><th>status / advise</th><th>Hub RSS</th></tr></thead><tbody>
<tr><td>100</td><td>50</td><td>0.7 / 4 ms</td><td>2 / 1 ms</td><td>69 MiB</td></tr>
<tr><td>300</td><td>149</td><td>0.8 / 2 ms</td><td>9 / 5 ms</td><td>78 MiB</td></tr>
<tr><td>1,000</td><td>477</td><td>0.8 / 15 ms</td><td>36 / 35 ms</td><td>109 MiB</td></tr></tbody></table>
<p>Simulated agents are threads of one process sharing two cores with the hub: latencies are upper bounds. At the 1,000-agent burst, 31 connections were reset (a real agent retries). Finding along the way: the server's listen backlog of 5 refused simultaneous reconnects; now 1,024.</p>
<div class="callout warn"><b>Limits</b>Everything above ran on one machine over loopback. No real network partition, clock skew or machine failure. Alerts come from the hub's heuristics: no custom rules, routing or acknowledgement. Details: <code>docs/HA.md</code>, <code>docs/INFRASTRUCTURE.md</code>.</div>''',
        [("Start a hub pair", '<span class="k">$ spatial serve hub --token-file t \\\n    --name a --peer B:7700 \\\n    --state-file a.json</span>'),
         ("Dashboard and alerts", '<span class="k">$ spatial dashboard --hub A:7700,B:7700 \\\n    --token-file ops.tok</span>\n<span class="d">dashboard (read-only, this machine only):\nhttp://127.0.0.1:PORT/?key=…</span>\n<span class="k">$ spatial watch --hub A:7700 \\\n    --token-file ops.tok</span>')])

    doc("roadmap", "Roadmap and open tests",
        "What is built, what needs hardware, and what needs people. Every item not yet tested is listed with how to run it.",
        '''<h2>Built and measured on one machine</h2>
<p>Planner (one objective, estimate against reality), console (accounts, organizations and roles, two-factor sign-in, API keys, jobs, usage, tax, numbered invoices with PDF, REST API), remote desktop for four Linux apps, fleet (agent, hub, fair share, gangs, affinity, persistence, failover, dashboard, alerts), accelerator fabric (CPU, Metal), portable kernels (incl. ARM64 via emulation), virtual interconnect, compute, tiered memory, runtime (micro-VM, WASM, Wine), security hardening.</p>
<h2>Needs hardware</h2>
<table><thead><tr><th>Item</th><th>Why it matters</th></tr></thead><tbody>
<tr><td>An NVIDIA GPU</td><td>Run the generated CUDA C and the <code>numba.cuda</code> path; price a GPU as a planner option. <b>Decides whether the commercial thesis holds.</b></td></tr>
<tr><td>Two or more real machines</td><td>Agents on real hosts, all-reduce on a real network, per-node speed instead of an assumption</td></tr>
<tr><td>A power meter (<code>sudo powermetrics</code>)</td><td>Energy per run is estimated today, not measured</td></tr>
<tr><td>An AMD GPU</td><td>Compile and run the generated HIP source</td></tr>
<tr><td>CXL, RDMA, Apple Silicon</td><td>Studied on paper or tested once</td></tr></tbody></table>
<h2>Needs people or accounts</h2>
<ul><li>Independent security review of the SWP/2 protocol and an adversarial test of the micro-VM sandbox.</li>
<li>A billed cloud run, to compare the planner's dollar estimate with an invoice.</li>
<li>Conversations with GPU cloud and inference operators, then a design-partner pilot with a measured saving.</li>
<li>Patent, trademark and export-control checks.</li></ul>
<h2>Not built</h2>
<ul><li>A Windows VM route (no licence); remote desktop beyond three Linux apps (audio, clipboard policy, several users); comparisons with Docker Desktop, UTM, Parallels, CrossOver.</li>
<li>Model routing, vLLM or llm-d, and GPU inference (a real small model was measured on the CPU: prefix reuse saved at least ×41 on a 946-token prompt, identical answers).</li>
<li>A replicated log for the hub, tiling and tensor cores in kernels, coverage-guided fuzzing.</li></ul>
<p>The full list with identifiers and procedures: <code>docs/TESTS_NOT_DONE.md</code> and <code>ROADMAP.md</code> in the repository. A weekly workflow (<code>verify.yml</code>) re-checks the properties behind the published results.</p>''',
        [("Re-check the claims", '<span class="k">$ python benchmarks/verify.py</span>\n<span class="d">PASS  interconnect: exact sums\nPASS  kernels: Metal == CPU\nPASS  fleet: 100 agents, no errors\n…</span>')])

    doc("changelog", "Changelog", "What changed in each release.",
        '''<h2>0.14.0</h2><ul><li>Hub majority election for three or more hubs (election safety, not a replicated log).</li>
<li>Kernels: whole-grid reductions with shared memory (Metal), HIP source generation, reserved-name checks.</li>
<li>Soak test, weekly re-verification workflow, new site pages.</li></ul>
<h2>0.13.0</h2><ul><li>Hub active/standby failover (about 6.7 s measured), read-only dashboard, alerts with optional webhook.</li></ul>
<h2>0.12.x</h2><ul><li>Virtual interconnect, portable kernels, fair share / gang / cache-affinity in the hub.</li>
<li>Protocol hardening (handshake timeout, connection cap, listen backlog), hub persistence, scale and fuzz tests.</li>
<li>Planner: a third probe when the first two cannot separate fixed cost from speed.</li></ul>
<h2>0.11.0</h2><ul><li>Accelerator fabric: one job on CPU, Metal or NVIDIA, chosen by measured cost.</li></ul>
<h2>0.10.0</h2><ul><li>One objective for every engine: the planner.</li></ul>
<h2>0.9.0</h2><ul><li>Fleet: agent, hub, recommendations.</li></ul>
<p>Full text: <code>CHANGELOG.md</code>.</p>''',
        [("Upgrade", '<span class="k">$ pip install -U spatial-computing</span>')])


# ---------------------------------------------------------------------------------------------------- French
def fr():
    doc("accelerators", "Accélérateurs et noyaux",
        "Un travail, décrit une fois, placé sur le périphérique le moins cher : CPU, GPU Metal, GPU NVIDIA ou nœud distant. Les noyaux s'écrivent une fois et sont générés pour chaque périphérique.",
        '''<div class="callout warn"><b>Périmètre</b>Le CPU et le GPU Metal sont testés sur un Mac. Les sources NVIDIA (C CUDA) et AMD (HIP) sont <b>générées, jamais compilées, jamais exécutées</b> : cette machine n'a aucun de ces GPU.</div>
<h2>Ce que ce n'est pas</h2>
<ul><li><b>Pas de l'émulation CUDA.</b> La licence de NVIDIA interdit les couches de traduction qui exécutent du code CUDA sur un autre matériel. Nous ne traduisons ni ne réimplémentons CUDA. ZLUDA (Apache-2.0/MIT) a été étudié et non utilisé : il demande un GPU AMD, que cette machine n'a pas, et il résout un autre problème (exécuter ailleurs des binaires CUDA existants).</li>
<li><b>Pas un remplaçant de l'orchestration NVIDIA</b> (KAI/Run:ai, Dynamo) : elle est open source ; nous nous y branchons au lieu de la concurrencer.</li></ul>
<h2>Le fabric</h2>
<p>Chaque périphérique exécute sa propre implémentation native du même travail. Le planificateur sonde chacune sur des tailles réduites, vérifie qu'elles s'accordent, et choisit la moins chère pour la taille réelle.</p>
<table><thead><tr><th>Périphérique</th><th>Moteur</th><th>État</th></tr></thead><tbody>
<tr><td>CPU</td><td>Numba, tous les cœurs</td><td>testé</td></tr>
<tr><td>GPU Metal</td><td>Metal Shading Language généré, compilé à l'exécution</td><td>testé (Intel Iris Plus 640)</td></tr>
<tr><td>GPU NVIDIA</td><td>C CUDA généré / <code>numba.cuda</code></td><td><b>jamais exécuté</b></td></tr>
<tr><td>GPU AMD</td><td>source HIP générée</td><td><b>jamais exécuté</b></td></tr>
<tr><td>Nœud distant</td><td>Hub de la flotte</td><td>testé en boucle locale</td></tr></tbody></table>
<h2>Noyaux portables</h2>
<p>Un noyau est un sous-ensemble typé de Python (<code>int</code>, <code>float32</code>, boucles, branches, <code>sin</code>, <code>sqrt</code>…). La même source donne du code CPU, du code Metal et une source CUDA/HIP. Le code non pris en charge est refusé avec un numéro de ligne.</p>
<pre><code>from spatial.kernel import kernel

@kernel
def collatz(i: int, j: int, n: int, limit: int):
    x = i * n + j + 1
    k = 0
    while x != 1 and k &lt; limit:
        if x % 2 == 0:
            x = x // 2
        else:
            x = 3 * x + 1
        k += 1
    return k

collatz.run("metal", 512, limit=1000)        # table n x n
collatz.reduce("metal", 512, limit=1000)     # somme sur la grille, en mémoire partagée
print(collatz.to_cuda_c(), collatz.to_hip())</code></pre>
<h2>Mesuré (MacBook Pro 2017, Intel Iris Plus 640)</h2>
<table><thead><tr><th>Vérification</th><th>Résultat</th></tr></thead><tbody>
<tr><td>Même travail, CPU ou Metal, périphérique choisi par le planificateur</td><td>7 tailles sur 7 correctes ; le croisement se situe entre n = 600 et n = 1 024</td></tr>
<tr><td>Noyau entier, CPU contre Metal</td><td>identique au bit près, y compris le dépassement 32 bits</td></tr>
<tr><td>Noyaux flottants</td><td>d'accord à l'arrondi float32 près (moins de 1 % de pixels de bordure différents)</td></tr>
<tr><td>Réduction en mémoire partagée, noyau entier</td><td>exacte face au CPU pour n = 16, 37, 100, 256</td></tr>
<tr><td>Choix du planificateur pour les noyaux portables</td><td>4 sur 6 corrects, regret moyen 1,09× ; les deux erreurs au point de croisement</td></tr></tbody></table>
<h2>Limites</h2>
<p>Deux formes de noyau (table 2-D, somme de toute la grille). Pas de tuilage, de cœurs tenseurs ni d'autres réductions. Le travail est modélisé en n² : les noyaux dépendants des données ne sont que grossièrement proportionnels. Détails : <code>docs/KERNELS.md</code>, <code>docs/FABRIC.md</code>.</p>''',
        [("Lancer", '<span class="k">$ spatial devices</span>\n<span class="k">$ spatial optimize compute \\\n    --family pk_collatz \\\n    --params \'{"n":1536,"limit":2000}\' \\\n    --execute</span>'),
         ("Collatz, 1536 × 1536", '<span class="d">cpu         597 ms\ngpu_metal    94 ms\nle planificateur a choisi gpu_metal\n(regret 1,00×)</span>')])

    doc("interconnect", "Interconnexion",
        "Opérations collectives entre processus sur le canal chiffré, avec l'algorithme choisi par un modèle de coût mesuré.",
        '''<div class="callout warn"><b>Pas un NVLink</b>NVLink, c'est du silicium et du cuivre. Ici, c'est une couche logicielle au-dessus du lien existant. Sur la machine de référence, la meilleure bande passante de bus est d'environ 0,2 à 0,3 Go/s ; NVLink 5 est annoncé à 900 Go/s par direction (chiffre du fabricant), soit environ <b>3 000 à 4 000 fois plus rapide</b>.</div>
<h2>Ce que ça fait</h2>
<p><code>spatial.interconnect</code> lance N processus qui échangent des données par SWP/2 (AES-256-GCM, confidentialité persistante). Il fournit all-reduce en anneau, halving-doubling et arbre, et la diffusion. Un modèle de coût <code>t = α + M/β</code> prédit le temps de chaque algorithme ; <code>allreduce(..., algo="auto")</code> prend le moins cher.</p>
<table><thead><tr><th>Algorithme</th><th>Temps prédit (M octets, N rangs)</th><th>Adapté à</th></tr></thead><tbody>
<tr><td>anneau</td><td>2(N−1)α + 2(N−1)/N · M/β</td><td>gros messages</td></tr>
<tr><td>halving-doubling</td><td>2·log₂N·α + 2(N−1)/N · M/β (N puissance de 2)</td><td>messages moyens</td></tr>
<tr><td>arbre</td><td>2·log₂N·(α + M/β)</td><td>petits messages</td></tr></tbody></table>
<h2>Mesuré</h2>
<ul><li>Tous les algorithmes donnent la somme exacte (tests).</li>
<li>Lien ajusté en boucle locale : α ≈ 150 à 200 µs par message, β ≈ 650 à 740 Mo/s.</li>
<li>Le modèle de lien unique partagé a choisi l'algorithme le plus rapide pour <b>1 taille sur 6</b> avec N = 4, 8 et 16 (4 sur 6 avec N = 6). Il préférait toujours halving-doubling ; en pratique l'arbre gagnait pour les petits messages et l'anneau pour les gros.</li>
<li>Calibrer chaque algorithme séparément corrige l'essentiel : jugé sur un nombre de rangs jamais vu, 3 à 5 sur 6 corrects, regret moyen de 1,07× à 1,27×. Les résultats varient d'une exécution à l'autre : lisez la tendance, pas un seul décompte.</li></ul>
<table><thead><tr><th>N = 8</th><th>anneau</th><th>halving-doubling</th><th>arbre</th></tr></thead><tbody>
<tr><td>1 Kio</td><td>10,4 ms</td><td>4,2 ms</td><td><b>2,0 ms</b></td></tr>
<tr><td>1 Mio</td><td>22,9 ms</td><td><b>13,8 ms</b></td><td>15,5 ms</td></tr>
<tr><td>16 Mio</td><td><b>228 ms</b></td><td>289 ms</td><td>369 ms</td></tr></tbody></table>
<h2>Limites</h2>
<p>Une machine, boucle locale, N = 4, 6, 8, 16 en processus sur deux cœurs (cela mesure autant la contention CPU qu'un lien). Pas de RDMA, pas de mémoire GPU, pas de tolérance aux pannes. NCCL, MPI, UCC et MSCCL++ sont matures : la valeur ici est une couche pilotée par un modèle de coût, chiffrée et neutre vis-à-vis du matériel, branchée sur le même planificateur. Détails : <code>docs/INTERCONNECT.md</code>.</p>''',
        [("Utilisation", '<span class="d">from spatial.interconnect import launch, allreduce\n\ndef work(comm):\n    x = local_vector(comm.rank)\n    return allreduce(comm, x, algo="auto")\n\nlaunch(8, work)</span>'),
         ("Pic de bande passante de bus", '<span class="d">cette couche  ~0,28 Go/s\nNVLink 5     900 Go/s (fabricant)\nrapport      ~3 200×</span>')])

    doc("operations", "Exploitation",
        "Faire tourner le hub de la flotte pour de vrai : redémarrages, bascule, tableau de bord local, alertes. Mesuré sur une machine ; ce qui n'est pas garanti est dit.",
        f'''<h2>Tableau de bord</h2>
<p><code>spatial dashboard</code> ouvre une page en lecture seule : nœuds avec barres de CPU, alertes, recommandations (les économies sont marquées comme estimations), locataires et file de tâches, plus le rôle et l'époque du hub. Elle est servie sur <b>127.0.0.1 uniquement</b> (aucune option pour écouter ailleurs), exige une clé aléatoire affichée au démarrage, refuse les en-têtes Host hors boucle locale (rebinding DNS) et n'accepte que GET. Pour une autre machine, utilisez un tunnel SSH.</p>
<p><img src="{CFG["prefix"]}../assets/dashboard.png" alt="Tableau de bord de la flotte avec une alerte de nœud arrêté" style="max-width:100%;border:1px solid var(--line)"></p>
<h2>Alertes</h2>
<p><code>spatial watch</code> et le bandeau du tableau de bord transforment les recommandations de gravité haute en événements : un quand une condition apparaît, un quand elle disparaît. <code>--webhook URL</code> les envoie en JSON ; cela envoie des données de la flotte à l'adresse indiquée.</p>
<h2>Persistance et redémarrage</h2>
<p><code>--state-file</code> sauvegarde les tâches, la file et l'usage par locataire toutes les 5 s (écriture atomique). Après un redémarrage, les tâches en cours sont remises en file (les charges sont des fonctions pures : les exécuter deux fois est sans danger) et les agents se reconnectent seuls. Les mesures des nœuds ne sont pas sauvegardées ; les agents les reconstruisent en un intervalle de rapport.</p>
<h2>Haute disponibilité</h2>
<table><thead><tr><th>Mode</th><th>Comment</th><th>Garantie</th></tr></thead><tbody>
<tr><td>Deux hubs</td><td><code>--peer</code> : actif et secours, le secours copie l'état et se promeut après 6 s</td><td>Bascule rapide ; <b>pas un consensus</b> : en cas de partition les deux peuvent être actifs, puis l'époque la plus basse s'efface et perd son état divergent</td></tr>
<tr><td>Trois hubs ou plus</td><td>deux <code>--peer</code> ou plus : élection à la majorité avec mandats, votes et baux</td><td>Au plus un chef par mandat ; un hub coupé de la majorité refuse les requêtes ; l'état circule encore par instantanés, donc jusqu'à une seconde de changements peut être perdue à la bascule ; pas un journal répliqué</td></tr></tbody></table>
<p>Mesuré sur un Mac, deux processus hub et un agent, <code>kill -9</code> sur le hub actif, 3 essais : une tâche soumise avant l'arrêt s'est terminée sur le survivant 6,7 s plus tard à chaque fois. Mode quorum : exécution aléatoire de 220 tours avec arrêts et redémarrages aléatoires de 5 hubs, aucun mandat n'a eu deux chefs (horloge simulée, vraies connexions en boucle locale).</p>
<h2>Endurance</h2>
<p>Test d'endurance (<code>benchmarks/soak.py</code>) : un hub, 3 agents, un client qui soumet une tâche toutes les 0,5 s avec des connexions qui tournent et un tableau de bord qui interroge, pendant 15 puis 12 minutes sur un Mac. Aucune erreur sur 1 758 et 1 419 tâches ; descripteurs de fichiers et fils d'exécution stables. Le premier essai a montré la mémoire du hub croissant de 12,5 Mio/h parce que les tâches terminées étaient gardées indéfiniment ; elles sont maintenant plafonnées (<code>--max-finished</code>). <b>Des minutes, pas des jours</b> : des fuites plus lentes ne sont pas exclues.</p>
<h2>Passage à l'échelle</h2>
<table><thead><tr><th>Agents</th><th>Rapports/s</th><th>Rapport p50 / p99</th><th>status / advise</th><th>RSS du hub</th></tr></thead><tbody>
<tr><td>100</td><td>50</td><td>0,7 / 4 ms</td><td>2 / 1 ms</td><td>69 Mio</td></tr>
<tr><td>300</td><td>149</td><td>0,8 / 2 ms</td><td>9 / 5 ms</td><td>78 Mio</td></tr>
<tr><td>1 000</td><td>477</td><td>0,8 / 15 ms</td><td>36 / 35 ms</td><td>109 Mio</td></tr></tbody></table>
<p>Les agents simulés sont des fils d'un même processus qui partagent deux cœurs avec le hub : les latences sont des majorants. Lors de la rafale de 1 000 agents, 31 connexions ont été réinitialisées (un vrai agent réessaie). Trouvaille en chemin : la file d'attente d'écoute du serveur (5) refusait les reconnexions simultanées ; elle est à 1 024.</p>
<div class="callout warn"><b>Limites</b>Tout ce qui précède a tourné sur une seule machine en boucle locale. Pas de vraie partition réseau, de dérive d'horloge ni de panne de machine. Les alertes viennent des heuristiques du hub : pas de règles personnalisées, d'acheminement ni d'accusé de réception. Détails : <code>docs/HA.md</code>, <code>docs/INFRASTRUCTURE.md</code>.</div>''',
        [("Lancer une paire de hubs", '<span class="k">$ spatial serve hub --token-file t \\\n    --name a --peer B:7700 \\\n    --state-file a.json</span>'),
         ("Tableau de bord et alertes", '<span class="k">$ spatial dashboard --hub A:7700,B:7700 \\\n    --token-file ops.tok</span>\n<span class="d">dashboard (lecture seule, cette machine) :\nhttp://127.0.0.1:PORT/?key=…</span>\n<span class="k">$ spatial watch --hub A:7700 \\\n    --token-file ops.tok</span>')])

    doc("roadmap", "Feuille de route et tests ouverts",
        "Ce qui est construit, ce qui demande du matériel, ce qui demande des gens. Chaque test non fait est listé avec la façon de le lancer.",
        '''<h2>Construit et mesuré sur une machine</h2>
<p>Planificateur (un objectif, estimation contre réalité), console (comptes, organisations et rôles, double authentification, clés d'API, jobs, usage, taxe, factures numérotées avec PDF, API REST), bureau distant pour quatre applications Linux, flotte (agent, hub, équité, groupes, affinité, persistance, bascule, tableau de bord, alertes), fabric d'accélérateurs (CPU, Metal), noyaux portables (dont ARM64 par émulation), interconnexion virtuelle, calcul, mémoire hiérarchisée, runtime (micro-VM, WASM, Wine), durcissement de la sécurité.</p>
<h2>Demande du matériel</h2>
<table><thead><tr><th>Élément</th><th>Pourquoi c'est important</th></tr></thead><tbody>
<tr><td>Un GPU NVIDIA</td><td>Exécuter le C CUDA généré et le chemin <code>numba.cuda</code> ; chiffrer un GPU comme option du planificateur. <b>Décide si la thèse commerciale tient.</b></td></tr>
<tr><td>Deux machines réelles ou plus</td><td>Agents sur de vrais hôtes, all-reduce sur un vrai réseau, vitesse par nœud au lieu d'une hypothèse</td></tr>
<tr><td>Un wattmètre (<code>sudo powermetrics</code>)</td><td>L'énergie par exécution est estimée aujourd'hui, pas mesurée</td></tr>
<tr><td>Un GPU AMD</td><td>Compiler et exécuter la source HIP générée</td></tr>
<tr><td>CXL, RDMA, Apple Silicon, plus de temps de matériel quantique</td><td>Étudiés sur le papier ou testés une fois</td></tr></tbody></table>
<h2>Demande des gens ou des comptes</h2>
<ul><li>Revue de sécurité indépendante du protocole SWP/2 et test adverse du bac à sable micro-VM.</li>
<li>Une exécution cloud facturée, pour comparer l'estimation en dollars du planificateur à une facture.</li>
<li>Des conversations avec des opérateurs de cloud GPU et d'inférence, puis un pilote avec un partenaire et une économie mesurée.</li>
<li>Vérifications de brevets, de marque et de contrôle des exportations.</li></ul>
<h2>Pas construit</h2>
<ul><li>Une route VM Windows (pas de licence) ; bureau distant au-delà de trois applications Linux (audio, politique de presse-papiers, plusieurs utilisateurs) ; comparaisons avec Docker Desktop, UTM, Parallels, CrossOver.</li>
<li>Routage de modèles, vLLM ou llm-d, et inférence sur GPU (un vrai petit modèle a été mesuré sur CPU : la réutilisation du préfixe a fait gagner au moins ×41 sur un prompt de 946 jetons, réponses identiques).</li>
<li>Un journal répliqué pour le hub, tuilage et cœurs tenseurs dans les noyaux, fuzzing guidé par la couverture.</li></ul>
<p>La liste complète avec identifiants et procédures : <code>docs/TESTS_NOT_DONE.md</code> et <code>ROADMAP.md</code> dans le dépôt. Un workflow hebdomadaire (<code>verify.yml</code>) revérifie les propriétés derrière les résultats publiés.</p>''',
        [("Revérifier les affirmations", '<span class="k">$ python benchmarks/verify.py</span>\n<span class="d">PASS  interconnect : sommes exactes\nPASS  noyaux : Metal == CPU\nPASS  flotte : 100 agents, sans erreur\n…</span>')])

    doc("changelog", "Journal des versions", "Ce qui change à chaque version.",
        '''<h2>0.14.0</h2><ul><li>Élection à la majorité du hub pour trois hubs ou plus (sûreté de l'élection, pas un journal répliqué).</li>
<li>Noyaux : réductions de toute la grille avec mémoire partagée (Metal), génération de source HIP, vérification des noms réservés.</li>
<li>Test d'endurance, workflow hebdomadaire de revérification, nouvelles pages du site.</li></ul>
<h2>0.13.0</h2><ul><li>Bascule du hub actif/secours (environ 6,7 s mesurées), tableau de bord en lecture seule, alertes avec webhook optionnel.</li></ul>
<h2>0.12.x</h2><ul><li>Interconnexion virtuelle, noyaux portables, équité / groupes / affinité de cache dans le hub.</li>
<li>Durcissement du protocole (délai de poignée de main, plafond de connexions, file d'écoute), persistance du hub, tests d'échelle et de fuzzing.</li>
<li>Planificateur : une troisième sonde quand les deux premières ne séparent pas le coût fixe de la vitesse.</li></ul>
<h2>0.11.0</h2><ul><li>Fabric d'accélérateurs : un travail sur CPU, Metal ou NVIDIA, choisi par le coût mesuré.</li></ul>
<h2>0.10.0</h2><ul><li>Un seul objectif pour tous les moteurs : le planificateur.</li></ul>
<h2>0.9.0</h2><ul><li>Flotte : agent, hub, recommandations.</li></ul>
<p>Texte complet : <code>CHANGELOG.md</code>.</p>''',
        [("Mettre à jour", '<span class="k">$ pip install -U spatial-computing</span>')])

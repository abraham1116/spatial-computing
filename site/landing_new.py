"""Landing page v2, product first: what the product does and what it brings. Limits live in the docs
(Limitations, Roadmap), not here. Every figure comes from a test or benchmark in the repository."""
import os

from scaffold import CFG, E, REPO, alt_url, head, nav

KERNEL = '''@kernel
def collatz(i: int, j: int, n: int, limit: int):
    x = i * n + j + 1
    k = 0
    while x != 1 and k < limit:
        if x % 2 == 0:
            x = x // 2
        else:
            x = 3 * x + 1
        k += 1
    return k

collatz.run("metal", 1536, limit=2000)   # 94 ms
collatz.run("cpu",   1536, limit=2000)   # 597 ms
print(collatz.to_cuda_c())               # and CUDA C / HIP source'''

ALLREDUCE = '''from spatial.interconnect import launch, allreduce

def work(comm):
    grad = local_gradient(comm.rank)
    # ring, halving-doubling or tree:
    # picked by a measured cost model
    return allreduce(comm, grad, algo="auto")

launch(8, work)    # 8 workers, encrypted links'''

HA = '''$ spatial serve hub --name a --peer B:7700 --state-file a.json
$ spatial serve hub --name b --peer A:7700 --state-file b.json
$ spatial agent --hub A:7700,B:7700 --token-file node.tok

kill -9 on the active hub
-> a new active hub in 5.6 s
-> the queued task finishes on the survivor 6.7 s later'''

T = {
 "en": dict(
  title="Spatial Computing — Run every job where it costs least",
  desc="The control layer for your compute infrastructure: it prices every way to run a job, runs the cheapest correct one, and proves the result.",
  eyebrow="Compute infrastructure · v{v} · open source",
  h1a="Run every job where it", h1b="costs least.",
  sub="Spatial Computing is the control layer for your compute infrastructure. It measures your machines, prices every way to run a job — CPU, GPU, a fleet, memory tiers, quantum — runs the cheapest one that stays correct, and records the estimate next to what really happened.",
  start="Get started", docs="Read the docs", frame="Fleet dashboard · live view of a 4-node fleet",
  eyeproof="Measured", proof_h="Numbers from the repository, not slides.",
  proof_lead="Each figure comes from a test or benchmark you can run yourself with <code>pytest</code> and <code>spatial bench all</code>.",
  stats=[("12 / 12","unseen cases where the planner picked the truly fastest option, each one run for real"),
         ("×31.6","faster than pure Python on the same job, identical result"),
         ("24 GiB","worked through a 512 MiB memory budget, 0 corrupt pages"),
         ("6.7 s","from a killed hub to a queued task finishing on the standby"),
         ("1,000","agents reporting to one hub, report latency p99 15 ms")],
  strip_note="Measured on a 2017 MacBook Pro (2 cores, 16 GB) on 14–15 November 2026. Methods and conditions: <a href=\"docs/results.html\">Results</a>.",
  gains_eye="What you get", gains_h="One objective. Every engine.",
  gains=[("Lower cost per job","One formula across every engine: the cheapest correct option within your deadline, memory and isolation limits, priced with the numbers you set."),
         ("More from the hardware you have","JIT and multi-core, a GPU when it pays, memory tiers that keep more data than RAM holds. The device is chosen by measurement, not by habit."),
         ("Infrastructure you can trust","Every decision is written to a tamper-evident ledger, every link is encrypted, and every estimate is compared with what happened and corrected.")],
  tour_eye="The product", tour_h="Everything you need to run compute at scale.",
  tour=[
   ("Planner","Ask once. See every option, priced.",
    "Describe a job and your limits. The planner proposes every way to run it across engines, ranks them with one formula, explains each refusal, and records its estimate next to the real result.",
    ["Compute, memory, runtime, quantum, AI and fleet options in one table","Calibrated by history: estimates improve with each run"],"docs/planner.html","PLAN"),
   ("Fleet","See every machine. Place work where it fits.",
    "An agent on each machine, a hub that sees them all. Work is placed by eligibility and load, shared fairly between teams, and recommendations come with their evidence.",
    ["Fair share between tenants, all-or-nothing gangs, cache-affinity routing","A read-only dashboard and alerts when a node goes quiet"],"docs/fleet.html","FLEET"),
   ("Accelerators","Write the kernel once. Run it on the cheapest device.",
    "One source in a typed Python subset becomes CPU code, a Metal GPU kernel and CUDA and HIP source. The planner probes each device and picks the cheapest for your size.",
    ["Integer kernels bit-identical on CPU and GPU","Shared-memory reductions on the GPU"],"docs/accelerators.html","KERNEL"),
   ("Interconnect","Collectives between workers, algorithm chosen for you.",
    "All-reduce and broadcast over encrypted links. A measured cost model picks ring, halving-doubling or tree for each message size and worker count.",
    ["Exact sums, verified on every algorithm","Calibrated per algorithm from your own measurements"],"docs/interconnect.html","ALLREDUCE"),
   ("Operations","Production-ready from the first hub.",
    "State survives restarts, a standby hub takes over on its own, three or more hubs elect a leader by majority, and agents follow the active hub without configuration.",
    ["Persistent queue and tenant history","Local dashboard behind a random key, alerts with an optional webhook"],"docs/operations.html","HA"),
  ],
  more_h="And the rest of the platform",
  more=[("Tiered memory","Work on data larger than RAM with a measured, priced latency trade-off.","docs/memory.html"),
        ("Runtime","Run software built for another system — Linux micro-VM, WebAssembly, Wine — isolated, with the route explained.","docs/runtime.html"),
        ("SPATIAL Q","One language for classical, distributed and quantum steps; simulators, Qiskit Aer and IBM hardware.","docs/spatialq.html"),
        ("AI","Reuse inference context instead of recomputing it, restored byte for byte.","docs/index.html"),
        ("Scientific and simulation","Numerical jobs checked against exact solutions; N-body energy drift under 0.1 %.","docs/index.html"),
        ("Holographic","Hologram synthesis and reconstruction, in focus on the emitted points.","docs/index.html")],
  prod_eye="Built for production", prod_h="Secure, observable, recoverable.",
  prod=[("Encrypted and authenticated","AES-256-GCM, forward-secret key exchange, scoped credentials with expiry, quotas and revocation."),
        ("Tamper-evident audit","Every decision and request goes into a hash-chained ledger you can verify."),
        ("High availability","Standby failover in seconds; majority election for three or more hubs."),
        ("Scale","1,000 agents on one hub, status in 36 ms, hub memory 109 MiB."),
        ("Hardware-neutral","CPU, Metal, CUDA and HIP generation, remote nodes: one job description, many devices."),
        ("Reproducible","Every claim has a test or benchmark. A weekly workflow re-checks them.")],
  q_eye="SPATIAL Q", q_h="A language for hybrid workflows.",
  q_lead="Classical, distributed and quantum steps in one program. The orchestrator picks a backend from a resource estimate.",
  band_h="Start in three minutes.", band_p="Install, run the audit, ask the planner. Open source under Apache-2.0.",
  oc_eye="Open core", oc_h="The core is open.", oc_p="The CLI, planner, fleet, SPATIAL Q, runtime and tiered-memory library are published under Apache-2.0. Advanced placement and cost policies are developed in a private package.",
  gh="GitHub", more_link="Learn more", lim="Limitations", measured="Measured on 14–15 November 2026 · 2017 MacBook Pro (i7-7660U, 2 cores, 16 GB)"),
 "fr": dict(
  title="Spatial Computing — Chaque travail là où il coûte le moins",
  desc="La couche de contrôle de votre infrastructure de calcul : elle chiffre chaque façon d'exécuter un travail, exécute la moins chère qui reste correcte, et prouve le résultat.",
  eyebrow="Infrastructure de calcul · v{v} · open source",
  h1a="Chaque travail là où il", h1b="coûte le moins.",
  sub="Spatial Computing est la couche de contrôle de votre infrastructure de calcul. Il mesure vos machines, chiffre chaque façon d'exécuter un travail — CPU, GPU, une flotte, des étages de mémoire, le quantique — exécute la moins chère qui reste correcte, et enregistre l'estimation à côté de ce qui s'est vraiment passé.",
  start="Commencer", docs="Lire la documentation", frame="Tableau de bord · vue en direct d'une flotte de 4 nœuds",
  eyeproof="Mesuré", proof_h="Des chiffres du dépôt, pas des diapositives.",
  proof_lead="Chaque chiffre vient d'un test ou d'un benchmark que vous pouvez lancer vous-même avec <code>pytest</code> et <code>spatial bench all</code>.",
  stats=[("12 / 12","cas inédits où le planificateur a choisi l'option vraiment la plus rapide, chacune exécutée pour de vrai"),
         ("×31,6","plus rapide que Python pur sur le même travail, résultat identique"),
         ("24 Gio","traités avec un budget mémoire de 512 Mio, 0 page corrompue"),
         ("6,7 s","entre un hub arrêté et une tâche en file terminée sur le secours"),
         ("1 000","agents qui rapportent à un hub, latence de rapport p99 15 ms")],
  strip_note="Mesuré sur un MacBook Pro 2017 (2 cœurs, 16 Go) les 14 et 15 novembre 2026. Méthodes et conditions : <a href=\"docs/results.html\">Résultats</a>.",
  gains_eye="Ce que vous obtenez", gains_h="Un objectif. Tous les moteurs.",
  gains=[("Un coût par travail plus bas","Une seule formule pour tous les moteurs : l'option correcte la moins chère dans vos limites de délai, de mémoire et d'isolation, avec les prix que vous fixez."),
         ("Plus du matériel que vous avez","JIT et multicœur, un GPU quand il rapporte, des étages de mémoire qui gardent plus de données que la RAM. Le périphérique est choisi par la mesure, pas par habitude."),
         ("Une infrastructure de confiance","Chaque décision est écrite dans un registre infalsifiable, chaque lien est chiffré, et chaque estimation est comparée à la réalité puis corrigée.")],
  tour_eye="Le produit", tour_h="Tout pour exploiter du calcul à grande échelle.",
  tour=[
   ("Planificateur","Demandez une fois. Voyez chaque option, chiffrée.",
    "Décrivez un travail et vos limites. Le planificateur propose toutes les façons de l'exécuter dans tous les moteurs, les classe avec une seule formule, explique chaque refus, et enregistre son estimation à côté du résultat réel.",
    ["Calcul, mémoire, runtime, quantique, IA et flotte dans un seul tableau","Calibré par l'historique : les estimations s'améliorent à chaque exécution"],"docs/planner.html","PLAN"),
   ("Flotte","Voyez chaque machine. Placez le travail où il convient.",
    "Un agent sur chaque machine, un hub qui les voit toutes. Le travail est placé selon l'éligibilité et la charge, partagé équitablement entre équipes, et les recommandations arrivent avec leurs preuves.",
    ["Équité entre locataires, groupes tout-ou-rien, routage par affinité de cache","Un tableau de bord en lecture seule et des alertes quand un nœud se tait"],"docs/fleet.html","FLEET"),
   ("Accélérateurs","Écrivez le noyau une fois. Exécutez-le sur le périphérique le moins cher.",
    "Une source dans un sous-ensemble typé de Python devient du code CPU, un noyau GPU Metal et des sources CUDA et HIP. Le planificateur sonde chaque périphérique et choisit le moins cher pour votre taille.",
    ["Noyaux entiers identiques au bit sur CPU et GPU","Réductions en mémoire partagée sur le GPU"],"docs/accelerators.html","KERNEL"),
   ("Interconnexion","Collectives entre processus, algorithme choisi pour vous.",
    "All-reduce et diffusion sur des liens chiffrés. Un modèle de coût mesuré choisit anneau, halving-doubling ou arbre pour chaque taille de message et nombre de processus.",
    ["Sommes exactes, vérifiées pour chaque algorithme","Calibré par algorithme à partir de vos propres mesures"],"docs/interconnect.html","ALLREDUCE"),
   ("Exploitation","Prêt pour la production dès le premier hub.",
    "L'état survit aux redémarrages, un hub de secours prend la relève seul, trois hubs ou plus élisent un chef à la majorité, et les agents suivent le hub actif sans configuration.",
    ["File et historique des locataires persistants","Tableau de bord local derrière une clé aléatoire, alertes avec webhook optionnel"],"docs/operations.html","HA"),
  ],
  more_h="Et le reste de la plateforme",
  more=[("Mémoire hiérarchisée","Travaillez sur des données plus grandes que la RAM avec un compromis de latence mesuré et chiffré.","docs/memory.html"),
        ("Runtime","Exécutez un logiciel conçu pour un autre système — micro-VM Linux, WebAssembly, Wine — isolé, avec la route expliquée.","docs/runtime.html"),
        ("SPATIAL Q","Un langage pour les étapes classiques, distribuées et quantiques ; simulateurs, Qiskit Aer et matériel IBM.","docs/spatialq.html"),
        ("IA","Réutilisez le contexte d'inférence au lieu de le recalculer, restauré octet pour octet.","docs/index.html"),
        ("Scientifique et simulation","Des travaux numériques vérifiés contre des solutions exactes ; dérive d'énergie N-corps sous 0,1 %.","docs/index.html"),
        ("Holographique","Synthèse et reconstruction d'hologrammes, nettes sur les points émis.","docs/index.html")],
  prod_eye="Conçu pour la production", prod_h="Sûr, observable, récupérable.",
  prod=[("Chiffré et authentifié","AES-256-GCM, échange de clés à confidentialité persistante, identifiants à portée limitée avec expiration, quotas et révocation."),
        ("Audit infalsifiable","Chaque décision et chaque requête entre dans un registre chaîné par hachage que vous pouvez vérifier."),
        ("Haute disponibilité","Bascule vers le secours en quelques secondes ; élection à la majorité à partir de trois hubs."),
        ("Passage à l'échelle","1 000 agents sur un hub, état en 36 ms, mémoire du hub 109 Mio."),
        ("Neutre vis-à-vis du matériel","CPU, Metal, génération CUDA et HIP, nœuds distants : une description de travail, plusieurs périphériques."),
        ("Reproductible","Chaque affirmation a un test ou un benchmark. Un workflow hebdomadaire les revérifie.")],
  q_eye="SPATIAL Q", q_h="Un langage pour les workflows hybrides.",
  q_lead="Étapes classiques, distribuées et quantiques dans un seul programme. L'orchestrateur choisit un moteur d'après une estimation de ressources.",
  band_h="Démarrez en trois minutes.", band_p="Installez, lancez l'audit, interrogez le planificateur. Open source sous Apache-2.0.",
  oc_eye="Open core", oc_h="Le cœur est ouvert.", oc_p="La CLI, le planificateur, la flotte, SPATIAL Q, le runtime et la bibliothèque de mémoire hiérarchisée sont publiés sous Apache-2.0. Les politiques avancées de placement et de coût sont développées dans un paquet privé.",
  gh="GitHub", more_link="En savoir plus", lim="Limitations", measured="Mesuré les 14 et 15 novembre 2026 · MacBook Pro 2017 (i7-7660U, 2 cœurs, 16 Go)"),
}


def render(lang: str, ctx: dict, version: str) -> str:
    t = T[lang]
    alt = alt_url(False, "index")
    pre = CFG["prefix"]
    vis = {"PLAN": ctx["PLAN"], "FLEET": ctx["FLEET"], "KERNEL": KERNEL, "ALLREDUCE": ALLREDUCE, "HA": HA}

    def vis_html(key):
        code = E(vis[key])
        if key == "PLAN":
            code = code.replace(">&gt; ", "<span class=\"g\">&gt;&gt; ", 1) if False else code
        return f'<pre><span class="d">{code}</span></pre>'

    console = os.environ.get("CONSOLE_URL")
    start_href = (console.rstrip("/") + "/#/signup") if console else "docs/quickstart.html"          # no console deployed: the quickstart is the way in
    p = [head(t["title"], t["desc"], "", alt), "<body>" + nav("", "home", alt), "<main>"]
    p.append(f'''<div class="lp-hero grid-bg"><div class="wrap">
<p class="eyebrow">{t["eyebrow"].format(v=version)}</p>
<h1>{t["h1a"]} <em>{t["h1b"]}</em></h1>
<p class="sub">{t["sub"]}</p>
<div class="row">
<pre class="install" id="inst" tabindex="0"><button class="copy" data-copy="inst" type="button">Copy</button>{E(ctx["INSTALL"])}</pre>
<div class="cta" style="display:flex;gap:12px;flex-wrap:wrap"><a class="btn" href="{start_href}">{t["start"]}</a><a class="btn ghost" href="docs/index.html">{t["docs"]}</a></div>
</div>
<div class="frame"><div class="bar"><i></i><i></i><i></i><span style="margin-left:8px">{t["frame"]}</span></div>
<div class="shot"><img src="{pre}assets/dashboard-hero.png" alt="Spatial Fleet dashboard: nodes, alerts, recommendations, tenants and queue" width="1280" height="860"></div></div>
</div></div>''')
    cells = "".join(f"<div><b>{E(n)}</b><span>{E(c)}</span></div>" for n, c in t["stats"])
    p.append(f'''<section id="proof"><div class="wrap">
<p class="eyebrow">{t["eyeproof"]}</p><h2>{t["proof_h"]}</h2><p class="lead">{t["proof_lead"]}</p>
<div class="strip">{cells}</div><p class="strip-note">{t["strip_note"]}</p>
</div></section>''')
    gains = "".join(f'<div><span class="n">0{i + 1}</span><h3>{E(h)}</h3><p>{E(b)}</p></div>' for i, (h, b) in enumerate(t["gains"]))
    p.append(f'''<section><div class="wrap"><p class="eyebrow">{t["gains_eye"]}</p><h2>{t["gains_h"]}</h2><div class="gains">{gains}</div></div></section>''')
    items = ""
    for name, head_, body, bullets, href, key in t["tour"]:
        lis = "".join(f"<li>{E(b)}</li>" for b in bullets)
        items += (f'<div class="item"><div class="txt"><p class="eyebrow">{E(name)}</p><h3>{E(head_)}</h3><p>{E(body)}</p><ul>{lis}</ul>'
                  f'<a class="more" href="{href}">{t["more_link"]} →</a></div><div class="vis">{vis_html(key)}</div></div>')
    minis = "".join(f'<div><h4><a href="{h}" style="text-decoration:none">{E(n)}</a></h4><p>{E(b)}</p></div>' for n, b, h in t["more"])
    p.append(f'''<section><div class="wrap"><p class="eyebrow">{t["tour_eye"]}</p><h2>{t["tour_h"]}</h2>
<div class="tour">{items}</div>
<h3 style="font-size:32px;margin:44px 0 16px">{t["more_h"]}</h3><div class="minis">{minis}</div></div></section>''')
    prod = "".join(f'<div><h4>{E(h)}</h4><p>{E(b)}</p></div>' for h, b in t["prod"])
    p.append(f'''<section><div class="wrap"><p class="eyebrow">{t["prod_eye"]}</p><h2>{t["prod_h"]}</h2><div class="minis">{prod}</div></div></section>''')
    p.append(f'''<section><div class="wrap split">
<div><p class="eyebrow">{t["q_eye"]}</p><h2>{t["q_h"]}</h2><p class="lead">{t["q_lead"]}</p><a class="btn ghost" href="docs/spatialq.html">{t["more_link"]}</a></div>
<div class="term"><div class="bar"><i></i><i></i><i></i><span style="margin-left:8px">examples/01_bell.sq</span></div><pre>{E(ctx["BELL"])}

<span class="d">$ spatial q run examples/01_bell.sq</span>
<span class="g">{E(ctx["Q_OUT"])}</span></pre></div>
</div></section>''')
    p.append(f'''<div class="band"><div class="wrap"><div><h2>{t["band_h"]}</h2><p>{t["band_p"]}</p>
<a class="btn" href="{start_href}">{t["start"]}</a> <a class="btn ghost" href="{REPO}" rel="noopener">{t["gh"]}</a></div>
<pre class="install" tabindex="0" style="margin:0">{E(ctx["INSTALL"])}</pre></div></div>''')
    p.append(f'''<section><div class="wrap split"><div><p class="eyebrow">{t["oc_eye"]}</p><h2>{t["oc_h"]}</h2><p class="lead">{t["oc_p"]}</p>
<a class="btn" href="docs/index.html">{t["docs"]}</a> <a class="btn ghost" href="{REPO}" rel="noopener">{t["gh"]}</a></div><div></div></div></section>''')
    p.append(f'''</main>
<footer><div class="wrap"><span>Spatial Computing · v{version} · Apache-2.0 · <a href="docs/limits.html">{t["lim"]}</a></span><span>{t["measured"]}</span></div></footer>
<script src="{pre}assets/app.js"></script></body></html>''')
    CFG["out"].mkdir(parents=True, exist_ok=True)
    (CFG["out"] / "index.html").write_text("".join(p))

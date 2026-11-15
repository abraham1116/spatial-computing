"""French content for the site (served under /fr/). Scaffolding lives in scaffold.py."""
from scaffold import *  # noqa: F401,F403
from scaffold import CFG, E, OUT, REPO, ROOT, alt_url, doc, head, nav, out_block
import scaffold as S

NAV_GROUPS = [
    ("Démarrer", [("index", "Vue d'ensemble"), ("quickstart", "Installation")]),
    ("Moteurs", [("planner", "Planificateur"), ("fleet", "Flotte"), ("compute", "Compute Engine"), ("memory", "Mémoire à étages"), ("runtime", "Runtime Engine"), ("spatialq", "SPATIAL Q")]),
    ("Référence", [("cli", "Commandes"), ("security", "Sécurité"), ("results", "Résultats"), ("limits", "Limitations")]),
]
UI = {"nav_label": "Principal", "proof": "Preuves", "install": "Installer", "docs_label": "Documentation", "examples_label": "Exemples"}

# ---------------------------------------------------------------- landing
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
    alt = alt_url(False, 'index')
    audit = "\n".join(OUT["audit"].splitlines()[:8])
    p = [head("Spatial Computing — Mesurer. Décider. Prouver.",
              "Choisit où et comment exécuter une charge à partir de mesures, et ne revendique un gain que s'il est mesuré.", "", alt)]
    p.append("<body>" + nav("", "home", alt))
    p.append(f'''<main>
<div class="hero grid-bg"><div class="wrap">
<div>
<p class="eyebrow">Un seul objectif · v0.12.1 · open source</p>
<h1>Mesurer.<br>Décider.<br><em>Prouver.</em></h1>
<p class="sub">Un seul objectif pour toute l'infrastructure : réaliser chaque travail correctement au moindre coût, et le prouver. Un planificateur chiffre chaque façon d'exécuter un travail à travers le calcul, la mémoire, le runtime, le quantique, l'IA, la science et une flotte de machines ; un agent par machine et un hub gardent les mesures honnêtes.</p>
<pre class="install" id="inst" tabindex="0"><button class="copy" data-copy="inst" type="button">Copier</button>{E(INSTALL)}</pre>
<div class="cta"><a class="btn" href="docs/quickstart.html">Démarrer</a><a class="btn ghost" href="#proof">Voir les mesures</a></div>
</div>
<div class="term" aria-label="Sortie réelle de la commande spatial audit"><div class="bar"><i></i><i></i><i></i><span style="margin-left:8px">$ spatial audit</span></div>
<pre><span class="d">{E(audit)}</span>
<span class="g">…</span></pre></div>
</div></div>

<section id="engines"><div class="wrap">
<p class="eyebrow">Un objectif, un cœur, tous les moteurs</p>
<h2>Tous les moteurs répondent à la même question.</h2>
<p class="lead">Quelle façon de faire ce travail est la moins chère, correcte, et dans mes contraintes ? Chaque moteur chiffre ses propres options ; le planificateur les classe avec une seule formule et consigne l'estimation à côté de ce qui s'est réellement passé. Ils partagent un modèle de données, un protocole chiffré et un registre infalsifiable en silence : un noyau quantique, un pas de simulation et une page mémoire sont ordonnancés et comptabilisés de la même façon.</p>
<div class="core"><span>Spatial Core</span><i>model · protocol · ledger · registry</i></div>
</div></section>

<section id="proof"><div class="wrap">
<p class="eyebrow">Mesuré, pas promis</p>
<h2>Une preuve par moteur.</h2>
<p class="lead">Chaque chiffre vient d'un test ou d'un benchmark du dépôt, exécuté sur un MacBook Pro 2017 (deux cœurs, 16 Go). Pour les refaire : <code>pytest</code> et <code>spatial bench all</code>.</p>
<div class="eng">
<div class="card"><h3>Planificateur</h3><p>Chiffre chaque façon d'exécuter un travail à travers tous les moteurs et choisit la moins chère.</p><div class="pf"><b>12 / 12</b><span>cas jamais vus où il a choisi l'option réellement la plus rapide, chacune exécutée pour de vrai ; erreur médiane d'estimation 5 %</span></div></div>
<div class="card"><h3>Flotte</h3><p>Voit toutes les machines d'un seul endroit et y place le travail.</p><div class="pf"><b>×1,66</b><span>12 tâches sur 3 agents contre 1, placées par le hub ; résultats identiques, chaîne d'audit intacte (une machine, 2 cœurs)</span></div></div>
<div class="card"><h3>Compute</h3><p>Exécute un calcul de la façon la moins chère que la machine permet.</p><div class="pf"><b>×31,6</b><span>JIT contre Python pur, résultat identique</span></div></div>
<div class="card"><h3>Mémoire à étages</h3><p>Traite plus de données que la RAM locale, pour un prix en latence mesuré.</p><div class="pf"><b>−75 %</b><span>de RAM locale en accès biaisé, pour 107× de latence moyenne</span></div></div>
<div class="card"><h3>Runtime</h3><p>Lance un logiciel conçu pour un autre système, isolé.</p><div class="pf"><b>0,88 s</b><span>pour démarrer une micro-VM Linux ; un .exe Windows tourne sous Wine</span></div></div>
<div class="card"><h3>SPATIAL Q</h3><p>Un langage pour les étapes classiques, distribuées et quantiques.</p><div class="pf"><b>1,000</b><span>de fidélité face à Qiskit jusqu'à 16 qubits ; une paire de Bell a tourné sur un vrai QPU IBM (90 % corrélée)</span></div></div>
<div class="card"><h3>IA</h3><p>Réutilise le contexte d'inférence au lieu de le recalculer.</p><div class="pf"><b>exact</b><span>le cache KV restauré donne la même sortie que le recalcul (modèle jouet, CPU)</span></div></div>
<div class="card"><h3>Scientifique</h3><p>Exécute un calcul numérique et vérifie sa réponse.</p><div class="pf"><b>2 / 2</b><span>calculs validés contre leur solution exacte</span></div></div>
<div class="card"><h3>Simulation</h3><p>Fait avancer des systèmes physiques.</p><div class="pf"><b>&lt; 0,1 %</b><span>de dérive d'énergie sur 400 pas à N corps</span></div></div>
<div class="card"><h3>Intelligence</h3><p>Prédit la meilleure stratégie avant de l'exécuter.</p><div class="pf"><b>confirmé</b><span>la prédiction issue des mesures passées désigne le gagnant mesuré</span></div></div>
<div class="card"><h3>Holographique</h3><p>Calcule des hologrammes pour de futurs écrans.</p><div class="pf"><b>au point</b><span>la reconstruction numérique tombe sur les points émis (aucun écran)</span></div></div>
</div>
<p class="note">Périmètre honnête : une seule machine. Rien n'est encore prouvé sur une seconde machine ou un GPU de centre de données, et le matériel quantique n'a exécuté qu'un circuit à deux qubits ; les moteurs IA, scientifique, simulation, intelligence et holographique sont de premiers composants, pas des produits.</p>
</div></section>

<section><div class="wrap">
<p class="eyebrow">Comment ça marche</p>
<h2>Une boucle, trois verbes.</h2>
<p class="lead">Chaque exécution produit une mesure. Chaque choix est consigné avec sa raison. Un résultat qui diffère de la référence est rejeté.</p>
<div class="cols3">
<div><h3>Mesurer</h3><p>Détecte le matériel réel, surveille CPU, RAM, compresseur et swap, et dit ce qu'il ne peut pas faire.</p><pre class="mini">$ spatial audit</pre></div>
<div><h3>Décider</h3><p>Compare les stratégies d'exécution et les routes (natif, micro-VM, WASM) et explique chaque refus.</p><pre class="mini">$ spatial plan app.exe
[ ] wine  Wine is not installed</pre></div>
<div><h3>Prouver</h3><p>Rejoue les benchmarks, régénère le tableau de résultats et conserve les échecs.</p><pre class="mini">$ spatial bench all</pre></div>
</div>
</div></section>

<section><div class="wrap split">
<div>
<p class="eyebrow">SPATIAL Q</p>
<h2>Un langage pour les flux hybrides.</h2>
<p class="lead">Classique, distribué et quantique dans un même programme. L'orchestrateur choisit le backend d'après une estimation de ressources, et refuse quand un circuit ne tient pas ou qu'aucun QPU n'est branché. Aucune accélération quantique n'est revendiquée : tout est simulé.</p>
<a class="btn ghost" href="docs/spatialq.html">Spécification</a>
</div>
<div class="term"><div class="bar"><i></i><i></i><i></i><span style="margin-left:8px">examples/01_bell.sq</span></div><pre>{E(BELL)}

<span class="d">$ spatial q run examples/01_bell.sq</span>
<span class="g">{E(OUT["q_bell"])}</span></pre></div>
</div></section>

<section><div class="wrap">
<p class="eyebrow">État réel</p>
<h2>Ce qui tourne, ce qui n'est qu'esquissé.</h2>
<p class="lead">Le statut de chaque moteur est déclaré dans le code, et un test interdit d'en afficher un sans preuve.</p>
<table><thead><tr><th>Moteur</th><th>Niveau</th><th>Pas encore fait</th></tr></thead><tbody>
<tr><td>Planificateur (l'objectif unique)</td><td><span class="tag ok">prototype opérationnel</span></td><td>Plusieurs machines, GPU, vraies factures, modèle appris</td></tr>
<tr><td>Flotte (agent + hub)</td><td><span class="tag ok">prototype opérationnel</span></td><td>Plusieurs vraies machines, passage à l'échelle, persistance du hub, tableau de bord</td></tr>
<tr><td>Compute Engine</td><td><span class="tag ok">prototype opérationnel</span></td><td>Seconde machine réelle, GPU Nvidia, mesure d'énergie</td></tr>
<tr><td>Mémoire à étages</td><td><span class="tag ok">prototype opérationnel</span></td><td>Pagination noyau, plusieurs écrivains, RDMA/CXL</td></tr>
<tr><td>Runtime Engine</td><td><span class="tag ok">prototype opérationnel</span></td><td>Conteneurs, GUI distante, applications Windows graphiques</td></tr>
<tr><td>SPATIAL Q</td><td><span class="tag ok">prototype opérationnel</span></td><td>QPU réel, QIR, sous-noyaux</td></tr>
<tr><td>AI</td><td><span class="tag part">premiers composants</span></td><td>Modèle jouet seulement : ni vrai LLM ni GPU</td></tr>
<tr><td>Scientifique, Simulation, Intelligence</td><td><span class="tag part">premiers composants</span></td><td>Solveurs métier, multiphysique, modèles appris</td></tr>
<tr><td>Holographique</td><td><span class="tag part">premiers composants</span></td><td>Optique numérique seulement : aucun écran</td></tr>
</tbody></table>
</div></section>

<section><div class="wrap split">
<div class="never"><h3 style="font-size:32px;margin-bottom:12px">Ce que Spatial ne fait pas</h3><ul>
<li>Il n'ajoute pas de RAM. La mémoire compressée, sur disque ou distante est typée <code>far_memory</code>, jamais <code>ram</code>.</li>
<li>Il ne confond pas virtualisation et ressource supplémentaire.</li>
<li>Il ne dit pas qu'un QPU accélère tout : le backend <code>qpu</code> refuse de s'exécuter tant qu'aucun fournisseur n'est configuré.</li>
<li>Il n'expose jamais la machine : les serveurs écoutent sur 127.0.0.1 et refusent toute autre adresse sans consentement explicite.</li>
</ul></div>
<div>
<p class="eyebrow">Open-core</p>
<h2>Le cœur est ouvert.</h2>
<p class="lead">CLI, audit, SPATIAL Q, runtime et bibliothèque mémoire sont publiés sous licence Apache-2.0. Les politiques avancées de placement et de coût sont développées dans un paquet privé, hors de ce dépôt.</p>
<a class="btn" href="docs/index.html">Lire la documentation</a> <a class="btn ghost" href="{REPO}" rel="noopener">GitHub</a>
</div>
</div></section>
</main>
<footer><div class="wrap"><span>Spatial Computing · v0.12.1 · Apache-2.0</span><span>Mesures du 14 novembre 2026 · MacBook Pro 2017 (i7-7660U, 2 cœurs, 16 Go)</span></div></footer>
<script src="{S.CFG["prefix"]}assets/app.js"></script></body></html>''')
    CFG["out"].mkdir(parents=True, exist_ok=True)
    (CFG["out"] / "index.html").write_text("".join(p))


def docs():

    doc("index", "Documentation", "Spatial Computing mesure, compare et choisit l'exécution d'une charge de travail. Voici où commencer.",
        '''<div class="paths">
<a href="quickstart.html"><b>Installer</b><span>Venv, dépendances, première commande en trois minutes.</span></a>
<a href="compute.html"><b>Compute Engine</b><span>Détecter, surveiller, comparer des stratégies, déporter.</span></a>
<a href="memory.html"><b>Mémoire à étages</b><span>Chaud, compressé, lointain : un échange chiffré, pas de la RAM.</span></a>
<a href="runtime.html"><b>Runtime Engine</b><span>Inspecter un binaire, choisir une route, l'exécuter isolé.</span></a>
<a href="spatialq.html"><b>SPATIAL Q</b><span>Langage, compilateur, OpenQASM 3, backends.</span></a>
<a href="results.html"><b>Résultats</b><span>Tous les chiffres mesurés et leurs conditions.</span></a>
</div>
<div class="callout"><b>Statut</b>Version 0.12.1. Quatre moteurs sont opérationnels et testés (142 tests) sur un seul Mac et en CI sous Linux. Rien n'a été prouvé sur une seconde machine, un GPU de centre de données ou un QPU. Voir <a href="limits.html">Limitations</a>.</div>
<h2>Principes</h2>
<ul><li><b>Une mesure avant toute affirmation.</b> Chaque exécution produit une <code>Measurement</code> ; les échecs sont conservés.</li>
<li><b>Résultat vérifié.</b> Une stratégie plus rapide n'est retenue que si elle calcule la même chose que la référence.</li>
<li><b>Refus explicites.</b> Ce que la machine ne peut pas faire est dit avec la raison, jamais simulé.</li>
<li><b>Aucune exposition réseau implicite.</b> Tout écoute en boucle locale par défaut.</li></ul>''',
        [("Première commande", f'<span class="k">$ spatial audit</span>\n<span class="d">{out_block("audit", 7)}</span>')])

    doc("quickstart", "Installation", "Python 3.10 ou plus récent. Testé sur macOS 13 (Intel) avec Python 3.13.",
        f'''<div class="callout"><b>Sur PyPI</b>Publié sous le nom <code>spatial-computing</code>. Pour travailler sur le code, clone le dépôt GitHub et lance <code>pip install -e ".[quantum,dev]"</code>.</div>
<h2>1. Environnement</h2>
<pre id="q1"><code>{E(INSTALL.splitlines()[0])}
{E(INSTALL.splitlines()[1])}</code></pre>
<p>L'extra <code>quantum</code> ajoute Qiskit, Qiskit Aer et l'importeur OpenQASM 3. Sans lui, SPATIAL Q fonctionne avec son simulateur intégré mais pas avec le backend <code>aer</code>.</p>
<p>Les versions de <code>numpy</code> (&lt; 2.2) et <code>numba</code> (&lt; 0.62) sont bornées : Numba 0.62 et plus a besoin d'un <code>llvmlite</code> qui ne se compile pas sur ce Mac.</p>
<h2>2. Vérifier</h2>
<pre><code>spatial audit
spatial status
pytest</code></pre>
<h2>3. Micro-VM Linux (facultatif)</h2>
<p>La route <code>microvm</code> du Runtime Engine demande QEMU (par exemple <code>sudo port install qemu</code> avec MacPorts) et deux fichiers téléchargés une fois dans <code>vendor/</code>, vérifiés par empreinte SHA-256.</p>
<pre><code>mkdir -p vendor &amp;&amp; cd vendor
curl -O https://dl-cdn.alpinelinux.org/alpine/v3.22/releases/x86_64/netboot/vmlinuz-virt
curl -o busybox-x86_64 https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox
shasum -a 256 -c SHA256SUMS</code></pre>
<h2>4. Binaires de test (facultatif)</h2>
<p>Pour reproduire les tests du runtime, installe l'extra <code>build</code> (compilateur croisé <code>ziglang</code>) puis lance <code>spatial bench runtime</code> : il compile le même programme C pour macOS, Linux, Windows et WASM dans <code>benchmarks/build/</code>.</p>''',
        [("Vérification", f'<span class="k">$ spatial status</span>\n<span class="d">Spatial Compute Engine          operational-prototype\nSpatial Resource Engine         operational-prototype\nSpatial Runtime Engine          operational-prototype\nSPATIAL Q                       operational-prototype\n…</span>'),
         ("Tests", '<span class="k">$ pytest</span>\n<span class="g">68 passed, 9 skipped</span>\n<span class="d"># les ignorés demandent benchmarks/build, QEMU ou Wine</span>')])

    doc("planner", "Planificateur", "Un seul objectif pour tous les moteurs : réaliser chaque travail correctement au moindre coût, et le prouver.",
        f'''<div class="callout"><b>L'objectif</b>Réaliser le travail <b>correctement</b> au plus bas <b>coût en dollars</b>, dans les contraintes que tu fixes (délai, RAM, isolation, matériel autorisé), et le <b>prouver</b> : l'estimation est consignée à côté de ce qui s'est réellement passé, et les estimations suivantes sont corrigées par cet historique.</div>
<h2>Comment les moteurs s'assemblent</h2>
<p>Chaque moteur a un fournisseur qui transforme un travail en options chiffrées. Une seule fonction les classe. Un seul registre garde la décision puis, après exécution, la mesure.</p>
<table><thead><tr><th>Moteur</th><th>Options proposées</th></tr></thead><tbody>
<tr><td>Compute, Simulation, Scientifique, Holographique</td><td>Chaque variante d'un calcul numérique (Python pur, NumPy, Numba, multi-cœurs), sondée sur des problèmes réduits et comparée aux autres</td></tr>
<tr><td>Flotte</td><td>Le même travail sur chaque nœud en ligne, au prix horaire du nœud</td></tr>
<tr><td>Fabric d'accélérateurs</td><td>Le même travail sur le CPU, un GPU Metal ou un GPU NVIDIA (le chemin NVIDIA est écrit, jamais exécuté sur du vrai matériel) ; sur le Mac de référence le planificateur a choisi le périphérique le plus rapide pour 7 tailles sur 7</td></tr>
<tr><td>Noyaux portables</td><td>Une source de noyau, exécutée sur le CPU ou un GPU Metal (le C CUDA est généré, jamais exécuté) ; le noyau entier est identique au bit près sur les deux ; bon choix de périphérique dans 4 cas sur 6, erreurs au point de croisement</td></tr>
<tr><td>Interconnexion virtuelle</td><td>All-reduce chiffré entre processus (anneau, halving-doubling, arbre), algorithme choisi par un modèle de coût mesuré ; sur une seule machine, environ 3 000 fois sous NVLink 5 en bande passante : c'est une couche logicielle, pas un remplaçant</td></tr>
<tr><td>Mémoire à étages</td><td>Un jeu de données en RAM ou en étages sur SSD, avec les latences mesurées sur cette machine</td></tr>
<tr><td>Runtime</td><td>Chaque route pour un binaire (natif, WASM, micro-VM, Wine) avec son isolation et son surcoût</td></tr>
<tr><td>SPATIAL Q</td><td>Simulateur exact, Aer, ou matériel réel (seulement si autorisé et chiffré)</td></tr>
<tr><td>IA</td><td>Un préfixe en cache : le recalculer, ou le garder et le restaurer</td></tr></tbody></table>
<h2>L'utiliser</h2>
<pre><code>{E(PLAN_CMDS)}</code></pre>
<h2>La décision est-elle bonne ?</h2>
<p>Chaque option réalisable a été exécutée pour de vrai et chronométrée, puis comparée au choix du planificateur (une machine, un prix horaire : le moins cher est le plus rapide).</p>
<table><thead><tr><th>Estimateur</th><th>Cas</th><th>A choisi le plus rapide</th><th>Erreur médiane d'estimation</th></tr></thead><tbody>
<tr><td>Une seule sonde</td><td>13</td><td>10 (77 %)</td><td>28 %</td></tr>
<tr><td>Deux tailles, ajustement affine</td><td>13</td><td>10 (77 %)</td><td>16 %</td></tr>
<tr><td>+ meilleur de plusieurs sondes</td><td>13</td><td>12 (92 %)</td><td>7 %</td></tr>
<tr><td>Idem sur 12 cas jamais utilisés pendant la mise au point</td><td>12</td><td>12 (100 %)</td><td>5 %</td></tr></tbody></table>
<p>Les premières versions classaient mal la variante multi-cœurs sur les travaux moyens : les sondes de quelques microsecondes étaient dominées par le bruit de démarrage des fils d'exécution. Garder le meilleur de plusieurs essais l'a corrigé.</p>
<div class="callout warn"><b>Limites</b>Une seule machine, 25 cas, noyaux numériques et simulation de circuits seulement. Les estimations sont propres à la machine (le planificateur resonde à chaque fois). L'étalonnage est une médiane des écarts passés, pas un modèle appris. Les coûts en dollars utilisent les prix que tu donnes : le prix local par défaut (0,134 $/h) est une hypothèse, un nœud sans prix est refusé, et un tarif de QPU n'est jamais deviné. Le moteur IA est un modèle jouet. Détails : <code>docs/OBJECTIVE.md</code>.</div>''',
        [("Exemple : calcul", f'<span class="d">{E(PLAN_HEAT)}</span>'), ("Exemple : données", f'<span class="d">{E(PLAN_DATA)}</span>')])

    doc("fleet", "Flotte", "Un agent sur chaque machine, un hub qui voit toute la flotte : mesurer, placer, recommander, auditer.",
        f'''<div class="callout warn"><b>Périmètre</b>Validé avec au plus 3 agents sur <b>une seule</b> machine. Les trois rapportent la même charge CPU : cela prouve la chaîne (identité, portées, placement, résultats, audit), pas le passage à l'échelle.</div>
<h2>Les pièces</h2>
<ul><li><b>Agent</b> (<code>spatial agent</code>) : mesure CPU, RAM, pression mémoire et GPU Nvidia toutes les quelques secondes, rapporte au hub, demande du travail et l'exécute. Connexions sortantes uniquement. Garde les mesures pendant une panne du hub et les livre avec leur heure d'origine.</li>
<li><b>Hub</b> (<code>spatial serve hub</code>) : conserve les mesures de chaque nœud, met en file et place les tâches, calcule l'utilisation et les recommandations. Il ne modifie jamais une machine de lui-même.</li>
<li><b>CLI opérateur</b> (<code>spatial fleet</code>) : état, recommandations, soumission, résultat.</li></ul>
<h2>Lancer</h2>
<pre><code>{E(RUN_FLEET)}</code></pre>
<h2>Placement</h2>
<p>Par tirage. Un agent demande du travail et reçoit la meilleure tâche en file qu'il peut prendre : priorité d'abord, puis ordre d'arrivée. Une tâche peut exiger un GPU, un minimum de RAM libre, une étiquette ou un nœud précis. Un nœud à 90 % de CPU ou plus ne reçoit rien. Chaque placement est consigné, avec sa raison, dans un journal chaîné par hachage. Les agents n'exécutent que des charges autorisées, désignées par leur nom : aucun code ne voyage vers un agent.</p>
<h2>Recommandations</h2>
<table><thead><tr><th>Type</th><th>Déclencheur</th></tr></thead><tbody>
<tr><td><code>node_down</code></td><td>Aucun rapport depuis 30 s</td></tr>
<tr><td><code>memory_pressure</code></td><td>Moins de 10 % de RAM libre</td></tr>
<tr><td><code>gpu_underused</code></td><td>GPU sous 20 % en moyenne</td></tr>
<tr><td><code>rebalance</code></td><td>Un nœud à 80 % ou plus à côté d'un nœud à 15 % ou moins</td></tr>
<tr><td><code>consolidate</code></td><td>Les cœurs occupés de la flotte tiendraient sur moins de nœuds à 60 % de cible, RAM vérifiée à 85 %</td></tr></tbody></table>
<p>Chacune montre ses preuves et ses hypothèses. Une économie en dollars n'apparaît que si tu as donné le prix de la machine (<code>--usd-per-hour</code>), et c'est une <b>estimation</b> : elle ne devient un résultat que lorsque tu appliques le changement et que tu mesures de nouveau la flotte.</p>
<h2>Sécurité</h2>
<p>Transport chiffré à confidentialité persistante. Avec des identifiants à portée limitée, l'identité d'un nœud est le nom de son identifiant : un agent ne peut pas se faire passer pour un autre, lire la flotte ni soumettre de tâches ; un lecteur ne peut pas injecter de mesures. Quotas, expiration, révocation et journal d'audit s'appliquent. Pas de revue indépendante.</p>
<h2>Limites</h2>
<p>Hub à processus unique et état en mémoire (ni persistance ni haute disponibilité), pas d'interface graphique, recommandations heuristiques, placement qui ne déplace pas le travail en cours. Description complète : <code>docs/INFRASTRUCTURE.md</code>.</p>''',
        [("Mesuré : 12 tâches, 1 agent contre 3", '<span class="d">1 agent     7,2 s\n3 agents    4,3 s  (x1,66)\nrésultats identiques à la référence : 12 / 12\nplacement : 6, 4, 2 tâches\n(une machine à 2 cœurs : gain borné)</span>'),
         ("spatial fleet status", f'<span class="d">{E(FLEET_STATUS)}</span>')])

    doc("compute", "Compute Engine", "Détecte le matériel, mesure son usage, compare des stratégies d'exécution et choisit la meilleure.",
        '''<h2>Détecter et surveiller</h2>
<p><code>spatial audit</code> lit le matériel réel (modèle, cœurs, jeu d'instructions SIMD, GPU, RAM, swap, stockage) et l'état courant : pression mémoire, taux du compresseur de macOS, ressources inactives, puis liste les limites qui en découlent.</p>
<h2>Comparer des stratégies</h2>
<p>Le <code>ComputeScheduler</code> exécute chaque stratégie d'un calcul de référence, mesure durée, temps CPU et mémoire de pointe, et <b>rejette tout résultat différent de la référence</b>. Stratégies fournies pour la charge de démonstration : Python pur, NumPy, Numba JIT, Numba multi-fils, pool de processus à froid et à chaud, worker distant, distribué local + worker.</p>
<pre><code>from spatial.compute import detect_node
from spatial.compute.scheduler import ComputeScheduler

sched = ComputeScheduler(detect_node())
rows = sched.compare("exp", {"n": 4000, "iters": 300}, sched.mandel_strategies())
best = sched.choose(rows, objective="time")   # "time" | "cpu" | "energy"</code></pre>
<h2>Déporter vers un worker</h2>
<p>Le worker n'exécute que des charges nommées dans une liste blanche : aucun code n'est transmis. Il écoute sur 127.0.0.1 et exige un jeton (HMAC).</p>
<pre><code>python3 -c "import os;open('token','wb').write(os.urandom(32))" &amp;&amp; chmod 600 token
spatial serve compute --token-file token</code></pre>
<div class="callout warn"><b>À savoir</b>Un worker lancé sur la même machine mesure le coût du protocole, pas le gain d'une seconde machine. Ce gain n'a pas encore été mesuré.</div>
<h2>Coûts</h2>
<p><code>CostModel</code> estime le coût local (électricité, amortissement) et cloud (heure facturée, facturation minimale, sortie réseau). Toute ligne cloud est étiquetée <code>estimated=True</code> : les prix sont des valeurs de liste non revérifiées et la vitesse cloud est supposée.</p>
<div class="callout"><b>Énergie</b>La jauge de batterie du Mac est restée figée à 32,5 W entre repos et pleine charge : l'énergie par exécution n'est pas mesurable avec elle. Il faut <code>powermetrics</code> (administrateur) ou un wattmètre.</div>''',
        [("Résultat mesuré (n = 700)", '<span class="d">Python pur            3,91 s\nNumPy                 1,13 s\nNumba JIT             0,124 s   ×31,6\nNumba 2 cœurs         0,061 s   ×64,5\nPool à froid          1,11 s\nPool à chaud          0,067 s</span>'),
         ("Audit", f'<span class="k">$ spatial audit</span>\n<span class="d">{out_block("audit", 8)}</span>')])

    doc("memory", "Mémoire à étages", "Adresser plus de données que le budget de RAM locale, en échangeant de la RAM contre du CPU et de la latence.",
        '''<div class="callout warn"><b>Ceci n'est pas de la RAM</b>L'étage compressé coûte du CPU. L'étage lointain coûte de la latence. Le type <code>far_memory</code> est distinct de <code>ram</code> dans tout le code, et un test l'impose.</div>
<h2>Les trois étages</h2>
<table><thead><tr><th>Étage</th><th>Contenu</th><th>Coût</th></tr></thead><tbody>
<tr><td>Chaud</td><td>Pages non compressées en RAM, LRU</td><td>Aucun</td></tr>
<tr><td>Compressé</td><td>Pages compressées (LZ4 ou zlib-1) et dédupliquées en RAM</td><td>CPU de compression</td></tr>
<tr><td>Lointain</td><td>Fichier sur SSD ou serveur de pages distant</td><td>Latence d'accès</td></tr></tbody></table>
<h2>Utilisation</h2>
<pre><code>from spatial.memory import TieredStore, FileBackend

st = TieredStore(hot_bytes=16 &lt;&lt; 20, compressed_bytes=16 &lt;&lt; 20,
                 far=FileBackend("/tmp/far.bin"),
                 prefetch=16, keep_far_copy=True)
st.put(0, page_bytes)
st.get(0)
print(st.stats())</code></pre>
<p><code>stats()</code> sépare toujours les octets logiques des octets réellement occupés en RAM locale, et donne par étage le taux de succès et la latence moyenne ou p50/p99.</p>
<h2>Optimisations mesurées</h2>
<ul><li><b>Lecture anticipée</b> sur détection de balayage séquentiel.</li><li><b>Conservation de la copie lointaine</b> d'une page non modifiée : sa prochaine éviction ne coûte aucune écriture.</li></ul>
<p>Sur un lien émulé à 0,2 ms, un balayage séquentiel passe de 2 605 à 2 047 µs par accès avec la lecture anticipée, puis à 1 305 µs avec la copie conservée.</p>
<h2>Limites</h2>
<p>Bibliothèque Python utilisée par API : ce n'est pas de la pagination transparente du noyau, et macOS n'en offre pas en espace utilisateur. Un seul écrivain, pas de chiffrement ni de réplication des pages lointaines. Les liens LAN et WAN des benchmarks sont <b>émulés</b>.</p>''',
        [("Exemple réel (16 Mo logiques)", f'<span class="d">{out_block("mem")}</span>'),
         ("Mesuré : 134 Mo de données, accès biaisé", '<span class="d">tout en RAM       0,76 µs/accès   134 Mo RAM\nétages + SSD     80,5 µs/accès    33,5 Mo RAM\nlien émulé 20 ms 13 957 µs/accès  8,4 Mo RAM\n                 (jeu de 33,6 Mo)</span>')])

    doc("runtime", "Runtime Engine", "Inspecte un binaire, énumère les routes d'exécution possibles avec la raison de chaque refus, et exécute la première réalisable.",
        '''<h2>Inspecter et planifier</h2>
<p><code>spatial plan</code> identifie le format (Mach-O, ELF, PE, WASM, script), le système et l'architecture visés d'après les en-têtes, puis liste les routes. Une route n'est marquée réalisable que si ses prérequis ont été détectés sur la machine.</p>
<h2>Exécuter</h2>
<p><code>spatial run</code> prend la première route réalisable (ou celle donnée par <code>--route</code>) et renvoie la sortie du programme.</p>
<table><thead><tr><th>Route</th><th>Usage</th><th>Isolation</th></tr></thead><tbody>
<tr><td><code>native</code></td><td>Même système et même processeur</td><td>Aucune</td></tr>
<tr><td><code>microvm-hvf</code></td><td>ELF Linux x86_64 sur hôte x86_64</td><td>VM matérielle, sans réseau ni disque</td></tr>
<tr><td><code>microvm-tcg</code></td><td>Autre processeur, en émulation logicielle</td><td>VM émulée</td></tr>
<tr><td><code>wasm-node-wasi</code></td><td>Modules WASM</td><td>Bac à sable WASI</td></tr>
<tr><td><code>wine</code></td><td>Binaires Windows (programme console testé)</td><td>Processus hôte (faible)</td></tr></tbody></table>
<div class="callout warn"><b>Windows</b>Avec Wine présent, un binaire Windows console s'exécute et rend la somme de référence. Sans Wine, le moteur le dit au lieu de faire semblant. Wine n'est jamais installé automatiquement (binaire tiers, accord de l'utilisateur requis). Les applications graphiques ne sont pas testées.</div>
<h2>Mesuré sur un même programme C</h2>
<table><thead><tr><th>Route</th><th>Calcul</th><th>Démarrage</th></tr></thead><tbody>
<tr><td>natif</td><td>1,00×</td><td>0,005 s</td></tr>
<tr><td>WASM / WASI</td><td>1,48×</td><td>0,07 s</td></tr>
<tr><td>micro-VM HVF</td><td>1,04×</td><td>0,88 s</td></tr>
<tr><td>micro-VM TCG (émulation)</td><td>23,8×</td><td>3,4 s</td></tr>
<tr><td>.exe Windows sous Wine</td><td>1,35 à 1,59×</td><td>environ 4,5 s</td></tr></tbody></table>
<p>Comparaison avec Docker Desktop, UTM, Parallels ou CrossOver : non faite, aucun n'est installé ici.</p>''',
        [("Binaire Windows", f'<span class="k">$ spatial plan bench-windows.exe</span>\n<span class="d">{out_block("plan_exe")}</span>'),
         ("ELF Linux", f'<span class="k">$ spatial plan bench-linux.elf</span>\n<span class="d">{out_block("plan_elf")}</span>\n\n<span class="k">$ spatial run bench-linux.elf 300 200</span>\n<span class="g">{out_block("run_elf")}</span>')])

    doc("spatialq", "SPATIAL Q", "Un langage de flux hybride : classique, distribué et quantique, avec choix de backend par estimation de ressources.",
        '''<div class="callout"><b>Honnêteté</b>Tout ce qui s'exécute est de la <b>simulation classique</b>. Aucun QPU n'est connecté et aucune accélération quantique n'est mesurée.</div>
<h2>Un programme</h2>
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
<h2>Noyaux, tâches, main</h2>
<ul><li><code>quantum</code> : circuit spécialisé pour ses arguments au moment de l'appel. Boucles et <code>if</code> classiques évalués à la compilation ; <code>measure</code> et rétroaction (<code>if m { x q[2]; }</code>) pour les circuits dynamiques.</li>
<li>Un noyau peut appeler des sous-noyaux à paramètres qubits : <code>quantum entangle(a: qubit, b: qubit) { h a; cx a, b; }</code>.</li>
<li><code>task … on cpu|worker|any</code> : travail classique, local ou déporté.</li>
<li><code>main</code> : orchestration ; <code>parallel { … }</code> lance des branches simultanées.</li></ul>
<h2>Portes</h2>
<p><code>h x y z s sdg t tdg sx</code> · <code>rx ry rz p</code> · <code>cx cz swap cp crz</code> · <code>ccx</code>. Les chaînes de bits suivent la convention de Qiskit (qubit 0 à droite).</p>
<h2>Chaîne de compilation</h2>
<p>Source → AST → circuit SQIR (représentation intermédiaire JSON) → optimiseur (annulation de paires inverses, fusion de rotations) → backend, ou export <b>OpenQASM 3</b>.</p>
<table><thead><tr><th>Backend</th><th>État</th></tr></thead><tbody>
<tr><td><code>statevector</code></td><td>Simulateur exact NumPy intégré</td></tr>
<tr><td><code>aer</code></td><td>Qiskit Aer (extra <code>quantum</code>)</td></tr>
<tr><td><code>qasm3</code></td><td>Export OpenQASM 3, rechargé avec succès par Qiskit dans un test</td></tr>
<tr><td><code>qir</code></td><td>Export QIR (profil de base) des circuits statiques, validé avec pyqir</td></tr>
<tr><td><code>qpu</code></td><td>IBM Quantum via <code>qiskit-ibm-runtime</code> (extra <code>qpu</code>). Demande un jeton et une instance ; sinon refuse en donnant la raison, sans repli silencieux. Une paire de Bell a tourné sur ibm_marrakesh : 90 % de résultats corrélés, le reste est du bruit matériel.</td></tr></tbody></table>
<h2>Refus de l'orchestrateur</h2>
<p>Un circuit dont le vecteur d'état (16 × 2<sup>n</sup> octets) dépasse la moitié de la RAM disponible est refusé avec un message explicite. Sur ce Mac : environ 27 qubits.</p>
<p>La grammaire complète est dans <code>docs/06_SPATIAL_Q_SPEC.md</code>.</p>''',
        [("Exécuter", f'<span class="k">$ spatial q run examples/01_bell.sq --seed 1</span>\n<span class="g">{out_block("q_bell")}</span>'),
         ("Exporter en OpenQASM 3", f'<span class="k">$ spatial q qasm examples/04_teleport.sq --args \'[1.0]\'</span>\n<span class="d">{out_block("q_qasm")}</span>'),
         ("Boucle hybride (VQE)", f'<span class="k">$ spatial q run examples/03_vqe_hybrid.sq</span>\n<span class="g">{out_block("q_vqe")}</span>\n<span class="d"># énergie exacte : -1.851199124123644</span>')])

    doc("cli", "Commandes", "Toutes les commandes de la ligne de commande <code>spatial</code>.",
        '''<table><thead><tr><th>Commande</th><th>Rôle</th></tr></thead><tbody>
<tr><td><code>spatial audit [--json]</code></td><td>Matériel, usage courant, limites de cette machine</td></tr>
<tr><td><code>spatial status</code></td><td>Statut réel de chaque moteur et ce qui n'est pas fait</td></tr>
<tr><td><code>spatial plan &lt;fichier&gt;</code></td><td>Format détecté et routes d'exécution, avec raisons</td></tr>
<tr><td><code>spatial run &lt;fichier&gt; [args] [--route R] [--timeout S]</code></td><td>Exécute via la première route réalisable ; code de sortie 1 si impossible</td></tr>
<tr><td><code>spatial q run|check|qasm|qasm2|qir|ir &lt;fichier.sq&gt; [--noise p] [--compiled]</code></td><td>Exécute (avec bruit dépolarisant en option), vérifie, exporte en OpenQASM 3, OpenQASM 2, QIR ou SQIR</td></tr>
<tr><td><code>spatial bench cpu|memory|gpu|runtime|q|all</code></td><td>Refait les mesures et régénère <code>docs/RESULTATS.md</code></td></tr>
<tr><td><code>spatial serve compute|memory|runtime --token-file F | --master-key-file F</code></td><td>Lance un worker, un serveur de pages ou un exécuteur de binaires en bac à sable, en boucle locale ; avec une clé maître, les locataires reçoivent des identifiants à portée limitée</td></tr>
<tr><td><code>spatial optimize compute|binary|quantum|dataset|kv [--objective cost|time --deadline S --max-ram-gib G --isolated --allow-qpu --execute]</code></td><td>L'objectif unique : chiffre toutes les options d'un travail, choisit la moins chère, l'exécute si demandé et compare à l'estimation</td></tr>
<tr><td><code>spatial devices</code></td><td>Périphériques de calcul que le planificateur peut utiliser sur cette machine</td></tr>
<tr><td><code>spatial agent --hub H:P --token-file F [--usd-per-hour X]</code></td><td>Lance un agent de flotte : mesure cette machine, rapporte à un hub, exécute des tâches autorisées</td></tr>
<tr><td><code>spatial fleet status|advise|submit|result --hub H:P --token-file F</code></td><td>Voir la flotte, obtenir des recommandations avec leurs preuves, soumettre et lire des tâches</td></tr>
<tr><td><code>spatial serve hub --master-key-file F</code></td><td>Lance le hub de la flotte</td></tr>
<tr><td><code>spatial token init|issue --master-key-file F [--name N --scopes S --ttl T --max-ops N --max-bytes B]</code></td><td>Crée une clé maître ; délivre un identifiant à portée, durée et quotas limités</td></tr></tbody></table>
<p>Une erreur affiche une seule ligne <code>spatial: Type: message</code> et renvoie le code 1.</p>''',
        [("Erreur propre", f'<span class="k">$ spatial run /nonexistent</span>\n<span class="d">{out_block("unknown")}</span>'),
         ("Vérifier un programme", f'<span class="k">$ spatial q check examples/05_ghz_qft.sq</span>\n<span class="g">{out_block("q_qpu")}</span>')])

    doc("security", "Sécurité", "Ce que le prototype protège, et ce qu'il ne protège pas encore.",
        '''<h2>En place</h2>
<ul><li><b>Boucle locale par défaut.</b> Lier une autre adresse lève <code>PermissionError</code> tant que <code>--allow-remote</code> n'est pas passé : c'est un acte explicite du propriétaire de la machine.</li>
<li><b>Authentification.</b> Jeton aléatoire de 32 octets (fichier en mode 600), défi-réponse HMAC-SHA256 ; un mauvais jeton est rejeté sans réponse.</li>
<li><b>Aucun code transmis.</b> Le worker n'exécute que des charges nommées dans une liste blanche.</li>
<li><b>Micro-VM fermée.</b> Aucun périphérique réseau, aucun disque, aucun dossier hôte ; RAM plafonnée.</li>
<li><b>Quota</b> de mémoire sur le serveur de pages.</li>
<li><b>Canal chiffré à confidentialité persistante.</b> Chaque enregistrement est scellé en AES-256-GCM ; les clés viennent d'un échange X25519 éphémère mêlé au secret : une session enregistrée reste illisible si le secret fuit plus tard. Un enregistrement modifié ou rejoué est rejeté.</li>
<li><b>Permissions à portée limitée.</b> Un serveur lancé avec une clé maître délivre des identifiants avec des portées (<code>run:mandel_numba</code>, <code>mem:read</code>, <code>exec:elf</code>), une expiration et des quotas ; chaque requête, acceptée ou refusée, va dans le journal d'audit.</li>
<li><b>Pages lointaines chiffrées et répliquées</b> avec <code>EncryptedBackend</code> et <code>ReplicatedBackend</code>.</li>
<li><b>Registre infalsifiable en silence.</b> Les mesures sont chaînées par hachage ; <code>Ledger.verify()</code> repère une ligne modifiée.</li></ul>
<h2>Pas encore en place</h2>
<ul><li>Une revue de sécurité indépendante. Aucune n'a été faite.</li>
<li>Identité par certificat (le secret est l'identité), journal d'audit <i>signé</i>, révocation et compteurs qui survivent à un redémarrage.</li>
<li>Bac à sable pour des charges arbitraires de tiers.</li></ul>
<div class="callout warn"><b>Ne pas exposer</b>N'utilise pas <code>--allow-remote</code> sur un réseau que tu ne contrôles pas : le protocole n'a pas fait l'objet d'une revue indépendante.</div>''',
        [("Refus d'une adresse publique", '<span class="d">RpcServer(handler, token, host="0.0.0.0")\n→ PermissionError: refusing to bind a\n  non-loopback address without\n  allow_remote=True (explicit user\n  consent required to expose this machine)</span>')])

    doc("results", "Résultats", "Chiffres mesurés le 14 novembre 2026 sur un MacBook Pro 2017 (Intel i7-7660U, 2 cœurs, 16 Go, macOS 13.7.8), sur secteur.",
        '''<div class="callout warn"><b>Conditions</b>Une seule machine, 1 à 5 répétitions, pas d'intervalle de confiance. Sur batterie faible, les mêmes tests étaient environ trois fois plus lents : le processeur est bridé.</div>
<table><thead><tr><th>Test</th><th>Résultat</th></tr></thead><tbody>
<tr><td>CPU, n = 700</td><td>Python pur 3,91 s · Numba 0,124 s (×31,6) · Numba 2 cœurs 0,061 s (×64,5)</td></tr>
<tr><td>CPU, n = 4000</td><td>1 fil 4,18 s · 2 cœurs 2,05 s (×2,04)</td></tr>
<tr><td>GPU intégré (Metal, float32)</td><td>20 à 33× les deux cœurs, face à une référence CPU non vectorisée</td></tr>
<tr><td>Mémoire du système</td><td>macOS tient 7,3 Gio de pages dans 2,1 Gio (taux 3,4)</td></tr>
<tr><td>Étages + SSD</td><td>33,5 Mo de RAM locale pour 134 Mo ; 80,5 µs/accès contre 0,76 µs</td></tr>
<tr><td>Jeu de données plus grand que la RAM</td><td>24 Gio avec un budget de 512 Mio sur un Mac de 16 Gio : 0 page corrompue sur 2 648 vérifiées, pic de RAM du processus 578 Mio, environ 5 ms par accès aléatoire (sur disque, une seule exécution)</td></tr>
<tr><td>Micro-VM Linux (HVF)</td><td>Démarrage 0,88 s ; calcul à 1,04× le natif</td></tr>
<tr><td>SPATIAL Q</td><td>Fidélité 1,000 face à Qiskit jusqu'à 16 qubits ; VQE à l'énergie exacte</td></tr>
<tr><td>SPATIAL Q sur matériel réel</td><td>5 circuits sur ibm_marrakesh ; le simulateur avec erreur de lecture asymétrique réduit de moitié l'écart avec la machine (un seul jeu de paramètres)</td></tr></tbody></table>
<h2>Reproduire</h2>
<pre><code>spatial bench all</code></pre>
<p>Le tableau complet, avec les hypothèses de coût, est généré dans <code>docs/RESULTATS.md</code>. Les coûts sont des estimations : aucune ressource cloud n'a été louée et l'énergie n'a pas pu être mesurée.</p>''',
        [("Reproduire", '<span class="k">$ spatial bench cpu</span>\n<span class="k">$ spatial bench memory</span>\n<span class="k">$ spatial bench runtime</span>\n<span class="k">$ spatial bench q</span>\n<span class="d"># écrit benchmarks/results/*.json\n# puis docs/RESULTATS.md</span>')])

    doc("limits", "Limitations", "Ce qui manque, dit sans détour.",
        '''<table><thead><tr><th>Limite</th><th>Conséquence</th></tr></thead><tbody>
<tr><td>Une seule machine</td><td>Déport et mémoire distante validés en boucle locale ou lien émulé ; aucun gain de capacité démontré</td></tr>
<tr><td>2 cœurs, GPU intégré sans float64</td><td>Parallélisme borné à ~2× ; pas d'inférence de modèle</td></tr>
<tr><td>Pas de CXL, RDMA, NPU, QPU</td><td>Étudiés sur documents seulement</td></tr>
<tr><td>Énergie non mesurable</td><td>Coûts énergétiques estimés</td></tr>
<tr><td>Windows</td><td>Un programme console exécuté sous Wine ; applications graphiques non testées</td></tr>
<tr><td>Protocole sans revue indépendante ; pas de certificats</td><td>Ne pas exposer à un réseau non maîtrisé</td></tr>
<tr><td>Simulation quantique exacte</td><td>~27 qubits ici, bornés par la RAM</td></tr>
<tr><td>Domaines AI, scientifique, simulation, intelligence, holographie</td><td>Premiers composants seulement (modèle jouet, petits solveurs, optique numérique)</td></tr></tbody></table>
<p>La liste détaillée et à jour est dans <code>docs/LIMITATIONS.md</code> (en anglais) ; chaque test non fait, avec la façon de le lancer, est dans <code>docs/TESTS_NOT_DONE.md</code>.</p>''',
        [("Statut des moteurs", '<span class="k">$ spatial status</span>\n<span class="d">compute / mémoire / runtime / SPATIAL Q\n  operational-prototype\nAI / scientifique / simulation /\nintelligence / holographique\n  first-components</span>')])


if __name__ == "__main__":
    landing()
    build_docs()
    print("built:", sorted(p.name for p in ROOT.glob("*.html")), sorted(p.name for p in (ROOT / "docs").glob("*.html")))

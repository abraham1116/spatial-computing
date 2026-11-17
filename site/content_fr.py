"""French content for the site (served under /fr/). Scaffolding lives in scaffold.py."""
from scaffold import *  # noqa: F401,F403
from scaffold import CFG, E, OUT, REPO, ROOT, alt_url, doc, head, nav, out_block
import scaffold as S
import pages_new
import pages_console

NAV_GROUPS = [
    ("Démarrer", [("index", "Vue d'ensemble"), ("quickstart", "Démarrage rapide")]),
    ("Console", [("console", "Console et comptes"), ("api", "API REST")]),
    ("Moteurs", [("planner", "Planificateur"), ("fleet", "Flotte"), ("compute", "Compute Engine"), ("memory", "Mémoire à étages"), ("runtime", "Runtime Engine"), ("spatialq", "SPATIAL Q"), ("accelerators", "Accélérateurs"), ("interconnect", "Interconnexion")]),
    ("Exploitation", [("operations", "Exploitation")]),
    ("Référence", [("cli", "Commandes"), ("security", "Sécurité"), ("results", "Résultats"), ("limits", "Limitations"), ("roadmap", "Feuille de route"), ("changelog", "Versions")]),
]
UI = {"start": "Commencer", "signin": "Connexion", "nav_label": "Principal", "proof": "Preuves", "install": "Installer", "docs_label": "Documentation", "examples_label": "Exemples"}

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
    import landing_new
    from spatial import __version__
    landing_new.render("fr", {"INSTALL": INSTALL, "PLAN": PLAN_HEAT, "FLEET": FLEET_STATUS, "BELL": BELL, "Q_OUT": OUT["q_bell"]}, __version__)


def docs():

    doc("index", "Documentation", "Spatial Computing mesure, compare et choisit l'exécution d'une charge de travail. Voici où commencer.",
        '''<div class="paths">
<a href="console.html"><b>Console</b><span>Créer un compte, une app, une clé d'API ; envoyer des jobs ; suivre l'usage et payer.</span></a>
<a href="quickstart.html"><b>Démarrage rapide</b><span>De zéro à un premier job, avec la console ou la CLI.</span></a>
<a href="api.html"><b>API REST</b><span>Tout ce que fait la console, pour les scripts.</span></a>
<a href="compute.html"><b>Compute Engine</b><span>Détecter, surveiller, comparer des stratégies, déporter.</span></a>
<a href="memory.html"><b>Mémoire à étages</b><span>Chaud, compressé, lointain : un échange chiffré, pas de la RAM.</span></a>
<a href="runtime.html"><b>Runtime Engine</b><span>Inspecter un binaire, choisir une route, l'exécuter isolé.</span></a>
<a href="spatialq.html"><b>SPATIAL Q</b><span>Langage, compilateur, OpenQASM 3, backends.</span></a>
<a href="accelerators.html"><b>Accélérateurs et noyaux</b><span>Un travail sur CPU, Metal, NVIDIA ou AMD ; noyaux écrits une fois.</span></a>
<a href="interconnect.html"><b>Interconnexion</b><span>Collectives chiffrées avec un modèle de coût mesuré.</span></a>
<a href="operations.html"><b>Exploitation</b><span>Bascule, tableau de bord, alertes, échelle.</span></a>
<a href="roadmap.html"><b>Feuille de route</b><span>Ce qui est construit, ce qui demande matériel ou personnes.</span></a>
<a href="results.html"><b>Résultats</b><span>Tous les chiffres mesurés et leurs conditions.</span></a>
</div>
<div class="callout"><b>Statut</b>Version 0.22.0. Quatre moteurs sont opérationnels et testés (274 tests) sur un seul Mac et en CI sous Linux. Rien n'a été prouvé sur une seconde machine, un GPU de centre de données ou un QPU. Voir <a href="limits.html">Limitations</a>.</div>
<h2>Principes</h2>
<ul><li><b>Une mesure avant toute affirmation.</b> Chaque exécution produit une <code>Measurement</code> ; les échecs sont conservés.</li>
<li><b>Résultat vérifié.</b> Une stratégie plus rapide n'est retenue que si elle calcule la même chose que la référence.</li>
<li><b>Refus explicites.</b> Ce que la machine ne peut pas faire est dit avec la raison, jamais simulé.</li>
<li><b>Aucune exposition réseau implicite.</b> Tout écoute en boucle locale par défaut.</li></ul>''',
        [("Première commande", f'<span class="k">$ spatial audit</span>\n<span class="d">{out_block("audit", 7)}</span>')])

    doc("quickstart", "Démarrage rapide", "De zéro à un premier job. Deux voies : la console (comptes, clés, jobs) ou la ligne de commande seule.",
        f'''<h2>Voie la plus rapide : la console</h2>
<ol><li>Ouvrez la console (<code>http://127.0.0.1:8090</code> si vous la lancez vous-même, voir <a href="console.html">Console et comptes</a>) et <b>créez un compte</b>.</li>
<li>Sur l'Overview, appuyez sur <b>New app</b>, puis créez une <b>clé nœud</b> et une <b>clé client</b> (API keys). Chacune n'est affichée qu'une fois : enregistrez-la.</li>
<li>Sur une machine : <code>pip install "spatial-computing[quantum]"</code>, puis <code>spatial agent --hub HUB:7700 --token-file node.tok</code>. Elle apparaît dans <b>Fleet</b>.</li>
<li>Ouvrez <b>Jobs</b>, choisissez <code>montecarlo_pi</code>, soumettez. Voyez le résultat, l'usage et la charge estimée dans <b>Usage &amp; billing</b>.</li></ol>
<p>Vous préférez les scripts ? Les mêmes étapes sont dans l'<a href="api.html">API REST</a>.</p>
<h2>Ligne de commande seule</h2>
<div class="callout"><b>Python 3.10 ou plus récent</b>Testé sur macOS 13 (Intel) avec Python 3.13.</div>
<div class="callout"><b>Sur PyPI</b>Publié sous le nom <code>spatial-computing</code>. Pour travailler sur le code, clone le dépôt GitHub et lance <code>pip install -e ".[quantum,dev]"</code>.</div>
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
         ("Tests", '<span class="k">$ pytest</span>\n<span class="g">196 passed, 1 skipped</span>\n<span class="d"># le test ignoré demande un outil non installé</span>')])

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
        f'''<div class="callout warn"><b>Périmètre</b>Validé sur <b>une seule</b> machine : jusqu'à 3 vrais agents, et 1 000 agents simulés (fils d'exécution) contre un hub. Cela prouve la chaîne (identité, portées, placement, résultats, audit) et les limites du hub sur une machine, pas le comportement sur un vrai réseau.</div>
<h2>Les pièces</h2>
<ul><li><b>Agent</b> (<code>spatial agent</code>) : mesure CPU, RAM, pression mémoire et GPU Nvidia toutes les quelques secondes, rapporte au hub, demande du travail et l'exécute. Connexions sortantes uniquement. Garde les mesures pendant une panne du hub et les livre avec leur heure d'origine.</li>
<li><b>Hub</b> (<code>spatial serve hub</code>) : conserve les mesures de chaque nœud, met en file et place les tâches, calcule l'utilisation et les recommandations. Il ne modifie jamais une machine de lui-même.</li>
<li><b>CLI opérateur</b> (<code>spatial fleet</code>) : état, recommandations, soumission, résultat.</li>
<li><b>Tableau de bord</b> (<code>spatial dashboard</code>) : une page en lecture seule dans votre navigateur, servie sur 127.0.0.1 uniquement, derrière une clé aléatoire affichée au démarrage ; nœuds, alertes, recommandations, locataires, file.</li>
<li><b>Alertes</b> (<code>spatial watch</code>, bandeau du tableau de bord) : une alerte quand une condition apparaît, une quand elle disparaît. Un webhook ne les reçoit que si vous passez <code>--webhook</code> ; cela envoie des données de la flotte hors de la machine.</li>
<li><b>Haute disponibilité</b> (<code>--peer</code>) : un hub actif et un hub de secours qui copie son état ; le secours se promeut après 6 s de silence et les agents suivent. Mesuré : environ 6,7 s entre <code>kill -9</code> et la fin d'une tâche sur le survivant. <b>Ce n'est pas un consensus</b> : en cas de partition, deux hubs peuvent être actifs jusqu'à ce qu'ils se revoient ; celui dont l'époque est la plus basse s'efface et perd son état divergent. Détails : <code>docs/HA.md</code>.</li></ul>
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
<p>Recommandations heuristiques ; placement qui ne déplace pas le travail en cours ; bascule sans journal répliqué (voir <a href="operations.html">Exploitation</a>) ; tout validé sur une seule machine. Description complète : <code>docs/INFRASTRUCTURE.md</code>.</p>''',
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
<tr><td><code>container</code></td><td>ELF Linux statique dans Docker ou Podman, même architecture que l'hôte, ou une architecture étrangère (ARM64) par émulation QEMU si enregistrée</td><td>Racine en lecture seule, sans réseau, sans capacités, non-root, 256 Mio ; réseau et dossier partagé seulement sur demande</td></tr>
<tr><td><code>desktop</code></td><td><code>spatial desktop xterm</code> (ou xclock, mousepad) : une application Linux graphique dans un conteneur, utilisée depuis votre navigateur via noVNC</td><td>Boucle locale seulement, mot de passe à usage unique, sans capacités, racine en lecture seule, 512 Mio</td></tr>
<tr><td><code>wasm-node-wasi</code></td><td>Modules WASM</td><td>Bac à sable WASI</td></tr>
<tr><td><code>wine</code></td><td>Binaires Windows (programme console testé)</td><td>Processus hôte (faible)</td></tr></tbody></table>
<div class="callout warn"><b>Windows</b>Avec Wine présent, un binaire Windows console s'exécute et rend la somme de référence. Sans Wine, le moteur le dit au lieu de faire semblant. Wine n'est jamais installé automatiquement (binaire tiers, accord de l'utilisateur requis). Une fenêtre graphique du Bloc-notes de Wine a été vue à l'écran ; aucune autre application graphique n'a été essayée.</div>
<h2>Mesuré sur un même programme C</h2>
<table><thead><tr><th>Route</th><th>Calcul</th><th>Démarrage</th></tr></thead><tbody>
<tr><td>natif</td><td>1,00×</td><td>0,005 s</td></tr>
<tr><td>WASM / WASI</td><td>1,48×</td><td>0,07 s</td></tr>
<tr><td>micro-VM HVF</td><td>1,04×</td><td>0,88 s</td></tr>
<tr><td>micro-VM TCG (émulation)</td><td>23,8×</td><td>3,4 s</td></tr>
<tr><td>.exe Windows sous Wine</td><td>1,35 à 1,59×</td><td>environ 4,5 s</td></tr></tbody></table>
<p>La route conteneur est testée avec Docker via Colima (chaque propriété d'isolation a un test) ; les mêmes tests passent aussi sur Podman. Comparaison avec Docker Desktop, UTM, Parallels ou CrossOver : non faite.</p>''',
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
<tr><td><code>spatial serve hub --master-key-file F [--state-file S] [--peer H:P --name N]</code></td><td>Lance le hub de la flotte ; avec un fichier d'état il survit aux redémarrages ; avec un pair il rejoint une paire actif/secours</td></tr>
<tr><td><code>spatial dashboard --hub H:P --token-file F</code></td><td>Tableau de bord en lecture seule sur 127.0.0.1, derrière une clé aléatoire</td></tr>
<tr><td><code>spatial watch --hub H:P --token-file F [--webhook URL]</code></td><td>Affiche les alertes quand elles apparaissent et disparaissent</td></tr>
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

    pages_new.fr()
    pages_console.render("fr")


if __name__ == "__main__":
    landing()
    build_docs()
    print("built:", sorted(p.name for p in ROOT.glob("*.html")), sorted(p.name for p in (ROOT / "docs").glob("*.html")))

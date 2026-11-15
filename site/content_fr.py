"""French content for the site (served under /fr/). Scaffolding lives in scaffold.py."""
from scaffold import *  # noqa: F401,F403
from scaffold import CFG, E, OUT, REPO, ROOT, alt_url, doc, head, nav, out_block
import scaffold as S

NAV_GROUPS = [
    ("Démarrer", [("index", "Vue d'ensemble"), ("quickstart", "Installation")]),
    ("Moteurs", [("compute", "Compute Engine"), ("memory", "Mémoire à étages"), ("runtime", "Runtime Engine"), ("spatialq", "SPATIAL Q")]),
    ("Référence", [("cli", "Commandes"), ("security", "Sécurité"), ("results", "Résultats"), ("limits", "Limitations")]),
]
UI = {"nav_label": "Principal", "proof": "Preuves", "install": "Installer", "docs_label": "Documentation", "examples_label": "Exemples"}

# ---------------------------------------------------------------- landing
INSTALL = """git clone https://github.com/abraham1116/spatial-computing && cd spatial-computing
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[quantum]"
spatial audit"""

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
<p class="eyebrow">Outils d'efficacité d'infrastructure · v0.4.0 · open source</p>
<h1>Mesurer.<br>Décider.<br><em>Prouver.</em></h1>
<p class="sub">Spatial choisit où et comment exécuter une charge de travail à partir de mesures, et ne revendique un gain que s'il est mesuré. Pas de RAM en plus : de l'utilisation en mieux.</p>
<pre class="install" id="inst" tabindex="0"><button class="copy" data-copy="inst" type="button">Copier</button>{E(INSTALL)}</pre>
<div class="cta"><a class="btn" href="docs/quickstart.html">Démarrer</a><a class="btn ghost" href="#proof">Voir les mesures</a></div>
</div>
<div class="term" aria-label="Sortie réelle de la commande spatial audit"><div class="bar"><i></i><i></i><i></i><span style="margin-left:8px">$ spatial audit</span></div>
<pre><span class="d">{E(audit)}</span>
<span class="g">…</span></pre></div>
</div></div>

<section id="proof"><div class="wrap">
<p class="eyebrow">Mesuré, pas promis</p>
<h2>Cinq chiffres, une seule machine.</h2>
<p class="lead">MacBook Pro 2017, Intel i7 à deux cœurs, 16 Go, sur secteur. Chaque chiffre est reproductible avec <code>spatial bench all</code> et détaillé dans les résultats complets.</p>
<div class="nums">
<div><b>×31,6</b><span>compilation JIT contre Python pur, même résultat vérifié</span></div>
<div><b>×2,04</b><span>deux cœurs contre un : la limite matérielle</span></div>
<div><b>0,88 s</b><span>démarrage d'une micro-VM Linux isolée sur macOS</span></div>
<div><b>−75 %</b><span>de RAM locale pour un jeu de données à accès biaisé, contre 107× de latence moyenne en plus</span></div>
<div><b>1,000</b><span>fidélité du simulateur SPATIAL Q face à Qiskit, jusqu'à 16 qubits</span></div>
</div>
<p class="note">Aucun gain venant d'une seconde machine n'a encore été démontré : il n'y avait qu'une machine. Le déport a été validé en boucle locale seulement.</p>
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
<footer><div class="wrap"><span>Spatial Computing · v0.4.0 · Apache-2.0</span><span>Mesures du 14 novembre 2026 · MacBook Pro 2017 (i7-7660U, 2 cœurs, 16 Go)</span></div></footer>
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
<div class="callout"><b>Statut</b>Version 0.4.0. Quatre moteurs sont opérationnels et testés (69 tests) sur un seul Mac et en CI sous Linux. Rien n'a été prouvé sur une seconde machine, un GPU de centre de données ou un QPU. Voir <a href="limits.html">Limitations</a>.</div>
<h2>Principes</h2>
<ul><li><b>Une mesure avant toute affirmation.</b> Chaque exécution produit une <code>Measurement</code> ; les échecs sont conservés.</li>
<li><b>Résultat vérifié.</b> Une stratégie plus rapide n'est retenue que si elle calcule la même chose que la référence.</li>
<li><b>Refus explicites.</b> Ce que la machine ne peut pas faire est dit avec la raison, jamais simulé.</li>
<li><b>Aucune exposition réseau implicite.</b> Tout écoute en boucle locale par défaut.</li></ul>''',
        [("Première commande", f'<span class="k">$ spatial audit</span>\n<span class="d">{out_block("audit", 7)}</span>')])

    doc("quickstart", "Installation", "Python 3.10 ou plus récent. Testé sur macOS 13 (Intel) avec Python 3.13.",
        f'''<div class="callout warn"><b>Pas encore sur PyPI</b>L'installation se fait depuis les sources du dépôt GitHub.</div>
<h2>1. Environnement</h2>
<pre id="q1"><code>{E(INSTALL.splitlines()[0])}
{E(INSTALL.splitlines()[1])}
{E(INSTALL.splitlines()[2])}</code></pre>
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
         ("Tests", '<span class="k">$ pytest</span>\n<span class="g">60 passed, 9 skipped</span>\n<span class="d"># les ignorés demandent benchmarks/build, QEMU ou Wine</span>')])

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
<tr><td><code>qpu</code></td><td>Non connecté : refuse de s'exécuter, sans repli silencieux</td></tr></tbody></table>
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
<tr><td><code>spatial q run|check|qasm|qasm2|qir|ir &lt;fichier.sq&gt; [--noise p]</code></td><td>Exécute (avec bruit dépolarisant en option), vérifie, exporte en OpenQASM 3, OpenQASM 2, QIR ou SQIR</td></tr>
<tr><td><code>spatial bench cpu|memory|gpu|runtime|q|all</code></td><td>Refait les mesures et régénère <code>docs/RESULTATS.md</code></td></tr>
<tr><td><code>spatial serve compute|memory|runtime --token-file F</code></td><td>Lance un worker, un serveur de pages ou un exécuteur de binaires en bac à sable, en boucle locale</td></tr></tbody></table>
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
<li><b>Canal chiffré.</b> Chaque enregistrement est scellé en AES-256-GCM avec une clé dérivée du jeton ; un enregistrement modifié ou rejoué est rejeté.</li>
<li><b>Pages lointaines chiffrées et répliquées</b> avec <code>EncryptedBackend</code> et <code>ReplicatedBackend</code>.</li>
<li><b>Registre infalsifiable en silence.</b> Les mesures sont chaînées par hachage ; <code>Ledger.verify()</code> repère une ligne modifiée.</li></ul>
<h2>Pas encore en place</h2>
<ul><li>Confidentialité persistante et identité des pairs : ajouter TLS ou WireGuard avant tout usage hors boucle locale.</li>
<li>Permissions par utilisateur ou par locataire, quotas CPU, journal signé.</li>
<li>Bac à sable pour des charges arbitraires de tiers.</li></ul>
<div class="callout warn"><b>Ne pas exposer</b>N'utilise pas <code>--allow-remote</code> sur un réseau que tu ne contrôles pas : le canal n'a ni confidentialité persistante ni identité par utilisateur.</div>''',
        [("Refus d'une adresse publique", '<span class="d">RpcServer(handler, token, host="0.0.0.0")\n→ PermissionError: refusing to bind a\n  non-loopback address without\n  allow_remote=True (explicit user\n  consent required to expose this machine)</span>')])

    doc("results", "Résultats", "Chiffres mesurés le 14 novembre 2026 sur un MacBook Pro 2017 (Intel i7-7660U, 2 cœurs, 16 Go, macOS 13.7.8), sur secteur.",
        '''<div class="callout warn"><b>Conditions</b>Une seule machine, 1 à 5 répétitions, pas d'intervalle de confiance. Sur batterie faible, les mêmes tests étaient environ trois fois plus lents : le processeur est bridé.</div>
<table><thead><tr><th>Test</th><th>Résultat</th></tr></thead><tbody>
<tr><td>CPU, n = 700</td><td>Python pur 3,91 s · Numba 0,124 s (×31,6) · Numba 2 cœurs 0,061 s (×64,5)</td></tr>
<tr><td>CPU, n = 4000</td><td>1 fil 4,18 s · 2 cœurs 2,05 s (×2,04)</td></tr>
<tr><td>GPU intégré (Metal, float32)</td><td>20 à 33× les deux cœurs, face à une référence CPU non vectorisée</td></tr>
<tr><td>Mémoire du système</td><td>macOS tient 7,3 Gio de pages dans 2,1 Gio (taux 3,4)</td></tr>
<tr><td>Étages + SSD</td><td>33,5 Mo de RAM locale pour 134 Mo ; 80,5 µs/accès contre 0,76 µs</td></tr>
<tr><td>Micro-VM Linux (HVF)</td><td>Démarrage 0,88 s ; calcul à 1,04× le natif</td></tr>
<tr><td>SPATIAL Q</td><td>Fidélité 1,000 face à Qiskit jusqu'à 16 qubits ; VQE à l'énergie exacte</td></tr></tbody></table>
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
<tr><td>Ni confidentialité persistante ni identité par utilisateur</td><td>Ne pas exposer à un réseau non maîtrisé</td></tr>
<tr><td>Simulation quantique exacte</td><td>~27 qubits ici, bornés par la RAM</td></tr>
<tr><td>Domaines AI, scientifique, simulation, intelligence, holographie</td><td>Premiers composants seulement (modèle jouet, petits solveurs, optique numérique)</td></tr></tbody></table>
<p>La liste détaillée est dans <code>docs/10_LIMITATIONS.md</code>.</p>''',
        [("Statut des moteurs", '<span class="k">$ spatial status</span>\n<span class="d">compute / mémoire / runtime / SPATIAL Q\n  operational-prototype\nAI / scientifique / simulation /\nintelligence / holographique\n  first-components</span>')])


if __name__ == "__main__":
    landing()
    build_docs()
    print("built:", sorted(p.name for p in ROOT.glob("*.html")), sorted(p.name for p in (ROOT / "docs").glob("*.html")))

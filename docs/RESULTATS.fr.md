# Résultats mesurés

Ce fichier est généré par `benchmarks/report.py` à partir des fichiers JSON de `benchmarks/results/`. Pour refaire les mesures : voir `README.md`. Les chiffres changent d'une exécution à l'autre (charge de fond, température, alimentation).

## Test 2 — CPU : local, optimisé, parallèle, distribué, distant

*Mesuré le 2026-11-14 23:58:02 +0100 — MacBookPro14,1, Intel(R) Core(TM) i7-7660U CPU @ 2.50GHz, macOS 13.7.8 — Now drawing from 'AC Power' (-InternalBattery-0 (id=6815843)	23%; charging; 2:25 remaining present: true).*

Problème : la même somme de contrôle Mandelbrot calculée par chaque stratégie ; une stratégie ne compte que si son résultat est identique à la référence. La compilation JIT est faite avant le chronométrage (durée : 1.65 s, pool de processus inclus). « Distant » et « distribué » utilisent un worker qui est **un processus sur ce même Mac** (boucle locale) : ils mesurent le surcoût du protocole, pas l'apport d'une seconde machine. La colonne CPU ne compte que le processus appelant et ses enfants terminés : elle **exclut** le worker et le pool persistant, d'où des valeurs proches de zéro sur ces lignes.

### mandel_small_slow_references — n = 700, itérations = 300, 1 répétition(s), médiane

| Stratégie | Type | Durée (s) | CPU (s) | CPU/durée | Accélération vs Python pur | Résultat identique |
|---|---|---|---|---|---|---|
| local_python | local | 3.91 | 3.87 | 0.99 | 1.00× | oui |
| local_numpy | optimized | 1.13 | 1.13 | 1.00 | 3.47× | oui |

### mandel_small_fast_strategies — n = 700, itérations = 300, 5 répétition(s), médiane

| Stratégie | Type | Durée (s) | CPU (s) | CPU/durée | Accélération vs Python pur | Résultat identique |
|---|---|---|---|---|---|---|
| local_numba_jit | optimized | 0.124 | 0.13 | 1.05 | 31.6× | oui |
| local_numba_threads | parallel | 0.0606 | 0.15 | 2.48 | 64.5× | oui |
| multiprocess_numba | parallel | 1.11 | 2.50 | 2.24 | 3.51× | oui |
| multiprocess_warm_pool | parallel | 0.0669 | 0.01 | 0.149 | 58.4× | oui |
| remote_worker | remote | 0.123 | 0.01 | 0.081 | 31.7× | oui |
| distributed_local+worker | distributed | 0.0699 | 0.09 | 1.29 | 55.9× | oui |

### mandel_large_fast_strategies — n = 4000, itérations = 300, 3 répétition(s), médiane

| Stratégie | Type | Durée (s) | CPU (s) | CPU/durée | Accélération vs Python pur | Résultat identique |
|---|---|---|---|---|---|---|
| local_numba_jit | optimized | 4.18 | 4.00 | 0.956 | — | oui |
| local_numba_threads | parallel | 2.05 | 4.13 | 2.01 | — | oui |
| multiprocess_numba | parallel | 3.39 | 6.55 | 1.93 | — | oui |
| multiprocess_warm_pool | parallel | 2.27 | 0.03 | 0.0132 | — | oui |
| remote_worker | remote | 4.16 | 0.01 | 0.0024 | — | oui |
| distributed_local+worker | distributed | 2.19 | 2.07 | 0.944 | — | oui |

Lecture :

- Compilation JIT : de l'ordre de 31.6× sur Python pur. C'est le gain dominant, et il est purement logiciel.
- Deux cœurs : 2.04× sur le grand cas — la limite matérielle attendue.
- Pool de processus à froid : 3.39 s contre 2.27 s à chaud. Le démarrage des processus et l'import des bibliothèques coûtent plus d'une seconde ; d'où le pool persistant (optimisation de l'étape 7).
- Worker en boucle locale : 4.16 s contre 4.18 s en local sur un fil — le protocole n'ajoute rien de mesurable à cette échelle. « Distribué » (2.19 s) égale les threads parce que le worker occupe le second cœur de la même machine. **Aucun gain de capacité n'a été démontré** : il faudrait un second ordinateur.
- Énergie : non mesurée (voir Limitations).

**Effet de l'alimentation (observation).** Une première exécution de ce même benchmark a été faite sur batterie entre 20 % et 11 % de charge ; son fichier JSON a été écrasé par l'exécution ci-dessus, les valeurs viennent du journal de console : Python pur 14,15 s, NumPy 6,27 s (n = 700) ; Numba un fil 11,68 s, Numba threads 5,88 s (n = 4000). Soit environ 2,8 à 3,6 fois plus lent que sur secteur. Le bridage du processeur sur batterie faible domine tous les autres effets : tout benchmark sur portable doit noter l'alimentation.

## Test 3 — GPU local (Metal) contre CPU

*Mesuré le 2026-11-14 23:58:49 +0100 — MacBookPro14,1, Intel(R) Core(TM) i7-7660U CPU @ 2.50GHz, macOS 13.7.8 — Now drawing from 'AC Power' (-InternalBattery-0 (id=6815843)	24%; charging; 2:21 remaining present: true).*

Même calcul en float32 des deux côtés (le GPU intégré n'a pas de float64). Le noyau GPU est un compute shader Metal compilé à l'exécution ; la référence CPU est Numba multi-fils. Les arrondis diffèrent (contraction FMA) : les sommes de contrôle sont comparées en écart relatif.

| n | Itérations | CPU Numba threads (s) | GPU Metal (s) | GPU / CPU | Écart relatif des sommes |
|---|---|---|---|---|---|
| 1024 | 300 | 0.134 | 0.00655 | 20.5× | 8.84e-06 |
| 2048 | 300 | 0.531 | 0.0239 | 22.2× | 1.07e-05 |
| 4096 | 300 | 2.14 | 0.0813 | 26.3× | 1.36e-05 |
| 2048 | 2000 | 3.45 | 0.105 | 32.9× | 1.25e-05 |

Périphérique : Intel(R) Iris(TM) Plus Graphics 640. Compilation du shader et création du pipeline : 0.245 s (hors chronométrage). Compilation Swift : 1.96 s.

Lecture : sur cette charge massivement parallèle, le GPU intégré est 20 à 30 fois plus rapide que les deux cœurs. **Réserve importante** : la référence CPU est scalaire (Numba ne vectorise pas cette boucle à sortie anticipée) ; une version AVX2 écrite à la main réduirait l'écart, d'un facteur non mesuré. Ce résultat ne se généralise pas : pas de float64, 1,5 Go de mémoire partagée, aucune pile d'inférence sérieuse ne cible ce GPU.

GPU distant : not tested: no remote GPU host or cloud account configured.

## Test 1 — Mémoire

*Mesuré le 2026-11-14 23:54:00 +0100 — MacBookPro14,1, Intel(R) Core(TM) i7-7660U CPU @ 2.50GHz, macOS 13.7.8 — Now drawing from 'AC Power' (-InternalBattery-0 (id=6815843)	19%; charging; 2:23 remaining present: true).*

### A. État réel de la mémoire du Mac

| Grandeur | Valeur |
|---|---|
| RAM totale | 16.0 Gio |
| RAM disponible | 6.90 Gio |
| Swap utilisé | 2.57 / 4.00 Gio |
| Pages tenues par le compresseur (taille logique) | 7.26 Gio |
| RAM occupée par le compresseur | 2.13 Gio |
| Taux de compression du système | 3.41 |
| Pression mémoire | normal |

macOS compresse déjà la mémoire froide : c'est la référence à battre, et elle est gratuite.

### B. Codecs selon le contenu (pages de 64 Kio)

| Contenu | Codec | Taux | Compression (Mo/s) | Décompression (Mo/s) |
|---|---|---|---|---|
| numeric | lz4 | 2.69 | 548 | 1 233 |
| numeric | zlib1 | 6.11 | 157 | 352 |
| text | lz4 | 4.61 | 699 | 2 988 |
| text | zlib1 | 7.68 | 282 | 508 |
| random | lz4 | 1 | 1 787 | 7 168 |
| random | zlib1 | 1 | 50.4 | 1 339 |

Le contenu décide de tout : des données aléatoires (ou déjà compressées, ou chiffrées) ne gagnent rien.

### C. Magasin à étages : latence d'accès par configuration

Jeu de données : pages de 64 Kio, 40 % numériques, 40 % texte, 20 % aléatoires. Chaque configuration tourne dans un processus neuf. « LAN émulé » et « WAN émulé » ajoutent un délai et un plafond de débit artificiels à un serveur de pages en boucle locale : **ce sont des émulations**, pas des mesures de réseau réel (et `sleep` dépasse sa consigne de quelques dizaines à centaines de microsecondes, ce qui les pessimise).

| Configuration | Accès | Logique (Mo) | RAM locale (Mo) | RSS pic (Mo) | Moyenne (µs/accès) | Chaud | Compressé | Lointain | p50 / p99 compressé (µs) | p50 / p99 lointain (µs) | CPU (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline all-in-RAM | zipf | 134 | 134 | 176 | 0.755 | 1.00 | 0 | 0 | — / — | — / — | 7.33 |
| tiered + SSD file | zipf | 134 | 33.5 | 74.4 | 80.5 | 0.651 | 0.162 | 0.186 | 193 / 574 | 210 / 632 | 9.00 |
| tiered + remote RAM (loopback) | zipf | 134 | 33.5 | 72.3 | 150 | 0.651 | 0.162 | 0.186 | 214 / 679 | 529 / 1 397 | 9.97 |
| tiered + remote RAM (LAN emulated 0.2 ms, 1 Gb/s) | zipf | 134 | 33.5 | 72.4 | 490 | 0.651 | 0.162 | 0.186 | 293 / 2 830 | 1 951 / 4 943 | 11.6 |
| tiered + remote RAM (WAN emulated 20 ms, 100 Mb/s) | zipf | 33.6 | 8.37 | 42.8 | 13 957 | 0.542 | 0.209 | 0.249 | 438 / 79 890 | 50 664 / 133 071 | 3.61 |
| uniform access, SSD file (worst case for tiering) | uniform | 134 | 33.5 | 76.9 | 206 | 0.12 | 0.287 | 0.593 | 190 / 502 | 209 / 605 | 11.2 |
| sequential scan LAN, no read-ahead | seq | 134 | 33.5 | 70.4 | 2 605 | 0 | 0 | 1.00 | — / — | 2 235 / 5 222 | 9.59 |
| sequential scan LAN, read-ahead 16 | seq | 134 | 33.5 | 74.1 | 2 047 | 0 | 0.94 | 0.0596 | 281 / 1 910 | 29 031 / 33 225 | 9.34 |
| sequential scan LAN, read-ahead 16 + clean-copy retention | seq | 134 | 33.5 | 74.8 | 1 305 | 0 | 0.94 | 0.0596 | 284 / 1 622 | 9 639 / 31 739 | 9.12 |
| zipf LAN + clean-copy retention | zipf | 134 | 33.5 | 72.2 | 394 | 0.651 | 0.162 | 0.186 | 286 / 2 195 | 1 496 / 5 119 | 11.3 |

Lecture :

- Tout en RAM : 0.755 µs par accès. Avec étages et SSD : 80.5 µs en moyenne, soit environ 107 fois plus lent, pour 33.5 Mo de RAM locale au lieu de 134 Mo (75.0 % de moins). C'est un échange, pas un gain : la mémoire économisée se paie en latence et en CPU.
- La RSS du processus baisse moins que la comptabilité interne (surcoût de l'interpréteur Python et des tampons).
- Accès uniforme : la majorité des accès tombent hors de l'étage chaud ; l'étagement n'a alors pas d'intérêt.
- Lien lent émulé à 20 ms : plus de dix millisecondes par accès en moyenne. Inutilisable pour autre chose que des données froides.
- Boucle d'optimisation sur le balayage séquentiel (LAN émulé) : 2 605 µs sans lecture anticipée → 2 047 µs avec lecture anticipée de 16 pages → 1 305 µs en conservant en plus la copie lointaine des pages non modifiées (×2.00 au total).
- **Aucune de ces configurations n'ajoute de RAM.** Elles permettent d'adresser plus de données que le budget de RAM locale, plus lentement.

## Test 4 — Runtime logiciel

*Mesuré le 2026-11-14 23:55:57 +0100 — MacBookPro14,1, Intel(R) Core(TM) i7-7660U CPU @ 2.50GHz, macOS 13.7.8 — Now drawing from 'AC Power' (-InternalBattery-0 (id=6815843)	21%; charging; 2:21 remaining present: true).*

Un même programme C compilé pour quatre cibles ; le moteur inspecte chaque binaire, choisit une route et l'exécute. La somme imprimée doit valoir 163059162 partout (n = 1500, itérations = 300).

| Binaire | Format détecté | Routes envisagées (réalisable ?) |
|---|---|---|
| bench-macos (32.3 Kio) | macho / macos / x86_64 | native (oui) |
| bench-linux.elf (1 328 Kio) | elf / linux / x86_64 | microvm-hvf (oui) ; microvm-tcg (oui) ; container (non) |
| bench-windows.exe (216 Kio) | pe / windows / x86_64 | native (non) ; wine (non) ; windows-vm (non) ; remote-windows (non) |
| bench.wasm (940 Kio) | wasm / any / wasm32 | wasm-node-wasi (oui) |

| Cible | Route | OK | Calcul dans l'application (ms) | Durée totale (s) | Démarrage (s) | Ralentissement vs natif | Somme correcte |
|---|---|---|---|---|---|---|---|
| macos-x86_64 | native | oui | 568 | 0.573 | 0.00457 | 1.00× | oui |
| wasm32-wasi | wasm-node-wasi | oui | 840 | 0.905 | 0.065 | 1.48× | oui |
| linux-x86_64 | microvm-hvf | oui | 589 | 1.47 | 0.879 | 1.04× | oui |
| linux-x86_64 | microvm-tcg | oui | 13 553 | 16.9 | 3.39 | 23.8× | oui |
| windows-x86_64 | aucune | **non** | — | — | — | — | — |

Lecture :

- Micro-VM Linux avec virtualisation matérielle (HVF) : calcul à quelques pour cent du natif, moins d'une seconde de démarrage, aucun réseau ni disque exposé.
- Même binaire en émulation logicielle (TCG) : plus de vingt fois plus lent. C'est le coût à attendre pour exécuter un autre jeu d'instructions (ARM sur ce Mac Intel).
- WASM sous Node/WASI : environ une fois et demie le temps natif, sans machine virtuelle.
- Binaire Windows : **non exécuté**. Raison rapportée par le moteur : native: host is not Windows; wine: Wine is not installed (not installed automatically: unsigned third-party build, needs user consent); windows-vm: no Windows image/licence on this machine; would run under QEMU+HVF; remote-windows: no remote Windows host configured.
- Environnement Python isolé avec une dépendance épinglée : créé en 3.45 s.
- Comparaison avec Docker Desktop, UTM, Parallels, CrossOver : non faite, aucun n'est installé.

## Test 5 — SPATIAL Q

*Mesuré le 2026-11-14 23:56:15 +0100 — MacBookPro14,1, Intel(R) Core(TM) i7-7660U CPU @ 2.50GHz, macOS 13.7.8 — Now drawing from 'AC Power' (-InternalBattery-0 (id=6815843)	21%; charging; 2:21 remaining present: true).*

Tout ce qui suit est de la **simulation classique** de circuits quantiques. Aucun QPU n'a été utilisé ; aucune accélération quantique n'est mesurée.

### Simulateur intégré contre Qiskit (mêmes circuits, 1000 tirs)

| Qubits | Portes | Compilation (s) | Vecteur d'état (Mo) | SPATIAL Q NumPy (s) | Qiskit Aer (s) | SPATIAL Q / Aer | Fidélité vs Qiskit |
|---|---|---|---|---|---|---|---|
| 4 | 44 | 0.000632 | 0.000256 | 0.00149 | 0.00512 | 0.291 | 1.000000000000 |
| 8 | 92 | 0.00126 | 0.0041 | 0.00274 | 0.00682 | 0.401 | 1.000000000000 |
| 12 | 140 | 0.00254 | 0.0655 | 0.00767 | 0.012 | 0.637 | 1.000000000000 |
| 16 | 188 | 0.00272 | 1.05 | 0.0659 | 0.0395 | 1.67 | 1.000000000000 |
| 20 | 236 | 0.00351 | 16.8 | 1.82 | 0.286 | 6.37 | non calculée |
| 22 | 260 | 0.00381 | 67.1 | 10.6 | 1.30 | 8.12 | non calculée |

Avec 7.14 Go disponibles au moment du test, la limite de simulation exacte sur ce Mac est d'environ **27 qubits** (16 × 2ⁿ octets, en gardant la moitié de la RAM libre).

Lecture : résultats numériquement identiques à Qiskit. Le simulateur NumPy est plus rapide qu'Aer sous 12 qubits (Aer a un coût fixe de lancement) et 6 à 8 fois plus lent à 20-22 qubits. Pour des circuits sérieux, le backend `aer` est le bon choix ; le simulateur intégré sert de référence indépendante.

### Optimiseur

| Noyau | Portes avant | Portes après | Passes | Compilation (s) |
|---|---|---|---|---|
| qft_roundtrip(4) | 20 | 0 | 7 | 0.00049 |
| qft_roundtrip(8) | 72 | 0 | 15 | 0.00178 |
| qft_roundtrip(12) | 156 | 0 | 23 | 0.00528 |

Ce cas (QFT suivie de son inverse) est construit pour s'annuler entièrement ; il vérifie l'optimiseur, il ne dit rien de son efficacité sur des circuits réels.

### Circuits dynamiques (téléportation, 4000 tirs)

| Méthode | Durée (s) |
|---|---|
| Simulation tir par tir (première version) | 0.9 |
| Énumération des branches de mesure (après optimisation) | 0.000348 |
| Qiskit Aer | 0.03 |

Gain de l'optimisation : ×2 587. Probabilité mesurée que le qubit téléporté vaille 1 : 0.227 ; attendue : 0.23.

### Programme hybride (VQE)

Énergie trouvée : -1.851199124 ; diagonalisation exacte : -1.851199124 ; écart : 0.0e+00. 905 évaluations de noyau quantique pilotées par la boucle classique, en 0.167 s.

## Test 6 — Coûts

**Aucun coût n'a été mesuré directement.** L'énergie n'a pas pu l'être (jauge de batterie figée, voir Limitations) et aucune ressource cloud n'a été louée. Le tableau applique le modèle de `spatial/compute/cost.py` aux durées mesurées, avec des hypothèses explicites.

Hypothèses : électricité 0,17 $/kWh ; puissance de la machine entière 32,5 W (seule lecture de jauge obtenue, sur batterie) ; prix à la demande AWS de mémoire, **non revérifiés** (c7i.large 0,0893 $/h, c7i.4xlarge 0,714 $/h) ; facturation minimale de 60 s ; rapports de vitesse cloud/local supposés (1,5× pour 2 vCPU récents, 12× pour 16 vCPU) ; portable à 1500 $ amorti sur 4 ans à 8 h/jour (hypothèse).

Charge : grand cas du test 2, meilleure stratégie locale (local_numba_threads, 2.05 s mesurées).

| Option | Durée | Coût par exécution | Nature |
|---|---|---|---|
| Local, matériel déjà payé | 2.05 s (mesuré) | 3.15e-06 $ d'électricité | durée mesurée, énergie estimée |
| Local, matériel amorti | 2.05 s (mesuré) | 7.64e-05 $ | estimation |
| AWS c7i.large | 1.37 s (supposé) | 1.49e-03 $ (facturé 60.0 s) | estimation |
| AWS c7i.4xlarge | 0.171 s (supposé) | 1.19e-02 $ (facturé 60.0 s) | estimation |

Coût horaire en charge continue (estimations) :

| Option | $/h | $/h ramené à la capacité locale |
|---|---|---|
| Local, électricité seule | 0.0055 | 0.0055 |
| Local, électricité + amortissement | 0.1339 | 0.1339 |
| AWS c7i.large (supposé 1,5× plus rapide) | 0.0893 | 0.0595 |
| AWS c7i.4xlarge (supposé 12× plus rapide) | 0.7140 | 0.0595 |

Lecture :

- Pour un travail de quelques secondes, le cloud coûte des centaines de fois plus cher que le local, uniquement à cause de la facturation minimale et sans compter le temps de démarrage d'instance.
- En charge continue, l'électricité locale est environ dix fois moins chère que l'instance cloud équivalente **si le matériel est déjà payé**. Si l'on compte l'amortissement d'un portable acheté pour cela, le cloud redevient moins cher par unité de travail.
- Donc : utiliser d'abord ce qu'on possède déjà et qui est inactif ; ne louer qu'au-delà. C'est une conclusion d'utilisation, pas de technologie.
- Mémoire : l'étagement économise de la RAM locale au prix de latence ; sa valeur en dollars dépend du prix de la DRAM et du coût de la latence pour l'application — non chiffré ici.
- Réseau : aucun transfert réel ; coût de sortie cloud non applicable aux tests.
- QPU : aucun tarif recherché ni mesuré.

**La question du brief — obtient-on plus de capacité pour moins cher ? — n'est pas tranchée par ces tests.** Ce qui est établi : un facteur de l'ordre de 30 à 60 obtenu en choisissant la bonne stratégie logicielle sur le même matériel, et un échange mémoire contre latence quantifié. Ce qui ne l'est pas : tout gain venant de ressources distantes.

## Statut des moteurs

| Engine | Status | Evidence | Not done |
|---|---|---|---|
| Spatial Compute Engine | operational-prototype | tests/test_compute.py, benchmarks/bench_cpu.py, bench_gpu.py | no real second machine tested (offload validated over loopback only); no GPU scheduling |
| Spatial Resource Engine (memory tiering) | operational-prototype | tests/test_memory.py, benchmarks/bench_memory.py | user-space object store only; not kernel paging; no RDMA/CXL hardware |
| Spatial Runtime Engine | operational-prototype | tests/test_runtime.py, benchmarks/bench_runtime.py | Windows apps not demonstrated (no Wine / Windows image); no GUI streaming |
| SPATIAL Q | operational-prototype | tests/test_q.py, benchmarks/bench_q.py | no real QPU executed (export to OpenQASM 3 only); simulator limited by RAM |
| Spatial AI Engine | first-components | tests/test_domains.py (placement planner) | no model inference executed; planner only |
| Spatial Scientific & Industrial Engine | first-components | tests/test_domains.py (Monte Carlo job via compute engine) | one reference job; no domain solvers |
| Spatial Simulation Engine | first-components | tests/test_domains.py (heat diffusion step) | single toy solver; no multiphysics |
| Spatial Intelligence Engine | first-components | tests/test_domains.py (runtime predictor) | least-squares runtime model only |
| Spatial Holographic Engine | interface-only | tests/test_domains.py (voxel data model) | no display hardware, no hologram synthesis; data model only |

# 01 — Étude technologique

Convention : **[FAIT]** = établi par une source citée ou mesuré ici ; **[HYPOTHÈSE]** = raisonnement plausible non vérifié ; **[SPÉCULATION]** = pari. Les sources sont listées en fin de document. Recherche menée le 14 novembre 2026 par requêtes web ; plusieurs chiffres proviennent de sources secondaires et sont signalés comme tels. Aucune base de brevets n'a été interrogée directement (voir `09_PROPRIETE_INTELLECTUELLE.md`).

## 1. La déclaration de Sam Altman — vérification

Le brief évoque une interview où Sam Altman aurait proposé d'utiliser les ressources inutilisées des ordinateurs personnels pour les infrastructures IA. **La recherche ne confirme pas cette lecture ; elle indique à peu près l'inverse.**

- **[FAIT]** L'épisode est le podcast *Cheeky Pint* (animé par John Collison), épisode 39, publié le 29 octobre 2026, vers la 29ᵉ minute, dans un passage sur l'inférence locale.
- **[FAIT, formulation approximative]** Phrase rapportée par la presse : « From a global allocation perspective, actually, it's quite terrible to have everybody have a bunch of the world's limited supply of DRAM sitting in their own computer and being used 5% of the time. » Aucune transcription complète n'a été trouvée ; les médias diffèrent légèrement sur les mots. À ne pas citer comme verbatim sans réécouter l'épisode.
- **[FAIT]** Le sens : dans un contexte de pénurie de DRAM, la mémoire est mieux utilisée dans un centre de données (fort taux d'utilisation) que dans des PC personnels. Il ne propose **pas** de mobiliser les PC des particuliers comme nœuds de calcul.
- **[FAIT]** Le chiffre de 5 % est son estimation, sans étude citée. Après la polémique, il a précisé vouloir que les gens puissent mettre autant de mémoire qu'ils veulent dans leurs ordinateurs.

Conséquence pour SPATIAL COMPUTING : l'argument de marché ne peut pas s'appuyer sur « Altman veut utiliser vos PC ». Ce qu'on peut en tirer est plus solide : **le dirigeant du plus gros acheteur de calcul au monde désigne publiquement le taux d'utilisation de la mémoire comme le problème.** C'est un problème d'utilisation, pas de décentralisation.

## 2. Mémoire : ce qui existe, ce qui marche, ce qui ne marche pas

### 2.1 Contexte économique
- **[FAIT, source secondaire citant TrendForce]** Prix contractuels de la DRAM conventionnelle : +90 à 95 % au T1 2026, +58 à 63 % au T2, +13 à 18 % au T3. Gartner prévoit +47 % sur l'année. Cause : bascule des capacités de production vers la HBM.
- **[FAIT, secondaire]** Un module RDIMM DDR5 64 Go pourrait coûter deux fois plus fin 2026 que début 2025. Les centres de données consommeraient ~70 % de la mémoire mondiale (IDC).

### 2.2 Mémoire lointaine logicielle (compression)
- **[FAIT]** Google, *Software-Defined Far Memory in Warehouse-Scale Computers* (Lagar-Cavilla et al., ASPLOS 2019) : compression proactive des pages froides via zswap ; 20 à 30 % des données migrées ; **4 à 5 % d'économie de TCO mémoire**, sans dégradation des indicateurs de service ; part de mémoire froide de 1 % à 52 % selon les machines. Le chiffre de 67 % concerne le coût du tiers lointain lui-même, pas le TCO total.
- **[FAIT, mesuré ici]** macOS fait la même chose en permanence : sur ce Mac, 6,9 Go de pages tiennent dans 2,05 Go (ratio 3,3).
- Leçon : la technique est mûre et déployée. Le gain réel à grande échelle est de quelques pour cent du coût mémoire — beaucoup en valeur absolue, modeste en proportion.

### 2.3 Mémoire distante (RDMA, pagination réseau)
- **[FAIT]** Infiniswap (NSDI 2017) : swap réparti en tranches sur la mémoire d'autres machines via RDMA.
- **[FAIT]** Fastswap (EuroSys 2020) : accès à une page distante en < 5 µs sur RDMA ; 10 Gb/s sur un fil d'exécution.
- **[FAIT]** AIFM (OSDI 2020) : mémoire lointaine intégrée à l'application, granularité objet ; jusqu'à 61× Fastswap sur certains cas. Motivation : ~30 % de la mémoire serveur est froide.
- **[FAIT]** Eden (NSDI 2025), Atlas : gains supplémentaires de 1,2 à 3× sur Fastswap.
- Limite commune : tout cela suppose un réseau de centre de données (RDMA, latence de quelques microsecondes). Aucun de ces résultats ne se transpose à un réseau domestique ou à Internet.

### 2.4 CXL
- **[FAIT, source promotionnelle]** Meta (webinaire du CXL Consortium, « Vistara ») : extension mémoire CXL déployée sur des millions de serveurs ; jusqu'à −25 % de serveurs pour l'inférence ML désagrégée ; latence 234 ns locale contre 280 ns CXL sous charge. Un autre texte donne 372 ns à 60 % de bande passante utilisée (+60 %).
- **[FAIT]** Marvell (Structera), Penguin (serveur de cache KV CXL 11 To), Samsung (CMM-D) livrent des produits. Le pooling multi-racks est attendu en production fin 2026-2027.
- Limite : CXL exige des serveurs récents et du matériel dédié. **Impossible sur un ordinateur portable et sur ce Mac.**

### 2.5 Le cas du PC personnel (8 Go de RAM, mémoire empruntée ailleurs)

| Question du brief | Réponse |
|---|---|
| Peut-on donner accès à de la mémoire d'une autre machine ? | **Oui techniquement, au niveau applicatif** (prototype `spatial.memory`). Non comme pagination transparente du noyau sur macOS : pas de périphérique de swap réseau accessible, pas d'API de pagination en espace utilisateur comparable à `userfaultfd`. Sous Linux : possible (swap sur NBD ou NVMe-oF, zswap, `userfaultfd`). |
| Une couche qui gère local + distant + stockage ? | Oui : c'est exactement ce que fait le prototype (chaud / compressé / lointain). |
| Transparent pour les applications ? | Seulement pour celles qui passent par l'API, ou sous Linux via le noyau. Pas pour une application macOS arbitraire. |
| Quelles applications en profitent ? | Celles dont l'accès est fortement biaisé (peu de données chaudes) ou séquentiel : caches, analytique par colonnes, jeux de données scientifiques, cache KV de LLM, onglets et documents dormants. |
| Lesquelles en souffrent ? | Accès aléatoire uniforme, temps réel, tout ce qui touche chaque page souvent : entraînement, bases en mémoire chaudes, jeux. |
| Latence | RAM locale ≈ 100 ns ; CXL ≈ 200-400 ns ; RDMA ≈ 3-5 µs ; SSD NVMe ≈ 50-100 µs ; LAN TCP ≈ 0,2-1 ms ; Internet ≈ 10-50 ms. Un défaut de page servi par Internet coûte 100 000 fois un accès RAM. |
| Cohérence | Simple si une seule machine écrit (cas du prototype). La mémoire partagée distribuée entre plusieurs écrivains reste un problème difficile (invalidation, ordre) ; hors périmètre. |
| Sécurité | Les pages quittent la machine : chiffrement obligatoire avant envoi (non implémenté dans le prototype, voir limites). |

**Conclusion [FAIT + mesure] :** sur un PC, le premier gisement n'est pas la mémoire distante mais la compression et le SSD NVMe local, déjà exploités par le système. La mémoire distante sur réseau domestique n'est intéressante que pour des données froides et volumineuses. Elle ne remplace jamais de la RAM.

## 3. Infrastructures IA

### 3.1 L'inefficacité mesurée
- **[FAIT]** Cast AI, *2026 State of Kubernetes Optimization Report* (télémétrie d'environ 23 000 clusters AWS/GCP/Azure) : **utilisation GPU moyenne de 5 %**. Critique recevable : un GPU « inactif » peut attendre des E/S ou du prétraitement ; l'échantillon est celui de clusters Kubernetes d'entreprise, pas de clusters d'entraînement bien gérés.
- **[FAIT, source secondaire]** Enquête VentureBeat T3 2026 : 79 % des entreprises disent qu'au moins la moitié de leur capacité GPU est inactive ; 70 % prévoient quand même d'en acheter.
- **[FAIT]** ClearML 2025-2026 : 44 % des organisations affectent les charges aux GPU à la main ou sans stratégie.
- **[FAIT]** Dépenses d'investissement 2026 de Microsoft, Amazon, Alphabet, Meta : environ 720 à 745 milliards de dollars cumulés ; Goldman Sachs estime ~180 milliards pour les GPU et accélérateurs.

### 3.2 Le cache KV, goulot mémoire de l'inférence
- **[FAIT]** Un modèle de 70 milliards de paramètres avec un contexte d'un million de jetons demande des centaines de Go de cache KV.
- **[FAIT]** llm-d (projet CNCF Sandbox, version 1.0 le 20 octobre 2026) : routage sensible au cache KV au-dessus de vLLM ; la documentation vLLM annonce 3× de débit et 2× sur le temps au premier jeton face au round-robin (Llama 3.1 70B) ; cache KV à étages (mémoire CPU, SSD local, stockage distant) ; désagrégation prefill/decode.
- **[FAIT]** Travaux 2026 : KVDrive (GPU/DRAM/SSD), ITME (CXL hybride), Samsung CMM-D, Nvidia CMX (étage flash). Un article coréen (KCC 2026) note que sur CXL-SSD, en cas de défaut, le temps de chargement du cache peut dépasser le temps de recalcul.
- **[FAIT]** Lacune relevée : aucun chiffre public de coût par jeton pour le cache KV à étages face au recalcul.

### 3.3 Calcul distribué sur machines grand public
- **[FAIT]** Petals (2022-2023) : BLOOM-176B à environ 1 pas par seconde sur GPU grand public ; les auteurs reconnaissent une latence élevée en génération jeton par jeton.
- **[FAIT, blog du projet]** Exo : le goulot est la latence entre appareils, pas le débit. Ses mesures portent sur du matériel homogène.
- **[FAIT, source secondaire]** Quatre Mac Studio haut de gamme en Thunderbolt 5 : 32,5 jetons/s contre 21,1 sur un seul. Le regroupement ajoute surtout de la capacité mémoire, peu de vitesse.
- Voir `02_ETUDE_CONCURRENTIELLE.md` pour les acteurs.

### 3.4 Difficultés réelles (liste du brief)

| Difficulté | Ordre de grandeur |
|---|---|
| Transfert des poids | 40 Go de poids à 50 Mb/s montants = près de 2 heures par nœud |
| Latence | Chaque coupure du pipeline ajoute un aller-retour par jeton : à 20 ms, dix coupures = 200 ms par jeton, soit 5 jetons/s au mieux |
| Disponibilité | Dix nœuds à 90 % chacun = chaîne disponible 35 % du temps (calculé par `spatial.ai.placement`) |
| Hétérogénéité | Le nœud le plus lent fixe le débit d'un pipeline |
| Confidentialité | Les activations en clair fuient le prompt ; le chiffrement homomorphe est des ordres de grandeur trop lent ; les enclaves GPU grand public n'existent pas |
| Énergie | Un PC de joueur tire 300-500 W en charge, avec un PUE domestique et un tarif résidentiel plus élevés qu'un centre de données |
| Fragmentation VRAM | 8 à 24 Go par carte ; les modèles utiles en demandent 40 à plus de 200 |

**Conclusion [HYPOTHÈSE argumentée] :** l'inférence interactive de grands modèles sur des PC de particuliers reliés par Internet n'est pas compétitive. Les charges qui s'y prêtent sont celles qui tolèrent latence et pannes : traitement par lots, embeddings, génération d'images, évaluation, ajustement fin de petits modèles, rendu. C'est le créneau déjà occupé par Salad, Vast.ai et io.net.

## 4. Runtime logiciel

- **[FAIT]** Conteneurs, machines virtuelles, Wine/Proton, WASM/WASI, bureau distant et diffusion d'applications sont des technologies mûres, largement ouvertes.
- **[FAIT, mesuré ici]** Un binaire Linux x86_64 démarre dans une micro-VM QEMU+HVF en environ une seconde sur ce Mac, avec un surcoût CPU faible ; le même programme en WASM tourne sous Node/WASI. Voir `RESULTATS.md`.
- **[FAIT]** Limites structurelles : macOS invité uniquement sur matériel Apple (licence et technique) ; Windows-sur-ARM et la traduction x86 dépendent de Microsoft et d'Apple ; les applications avec GPU, anti-triche ou pilotes noyau résistent à Wine.
- **[HYPOTHÈSE]** La valeur n'est pas dans une nouvelle technique d'isolation mais dans la **décision automatique** : inspecter un artefact, choisir la route (natif, VM, WASM, Wine, distant) selon le matériel, le coût et l'isolation requise.

## 5. Calcul quantique

- **[FAIT]** QIR (LLVM) est le standard de fait entre langages et plateformes ; OpenQASM 3 couvre les circuits dynamiques ; CUDA-Q compile vers QIR et exécute sur simulateurs CPU/GPU ; un article d'avril 2026 décrit la transpilation OpenQASM 3 → CUDA-Q.
- **[FAIT]** IBM et Algorithmiq ont annoncé le 30 juillet 2026 une démonstration d'avantage quantique (simulation d'un matériau quantique hétérogène), comparée aux meilleures méthodes classiques du Flatiron Institute. IBM attend une vérification par la communauté d'ici fin 2026 : **la revendication est ouverte à contestation**, comme les précédentes.
- **[FAIT]** Une étude de novembre 2026 recense 24 problèmes à accélération quantique possible, en soulignant qu'un algorithme quantique peut demander moins d'étapes et rester plus lent en temps réel.
- **[FAIT]** Aucune démonstration d'avantage sur un problème d'intérêt commercial courant (optimisation logistique, finance, apprentissage) n'a été trouvée.
- Où un QPU peut aider [consensus scientifique] : simulation de systèmes quantiques (chimie, matériaux), factorisation et logarithme discret (Shor, à très long terme, avec correction d'erreurs), certains problèmes d'échantillonnage. Où il n'aide pas : calcul généraliste, entraînement de réseaux, bases de données, la quasi-totalité des charges d'entreprise.
- Limites économiques [FAIT général] : accès facturé au tir ou à la minute, files d'attente, bruit, et besoin d'un grand nombre de qubits physiques par qubit logique.

**Conséquence pour SPATIAL Q :** un nouveau langage quantique n'a pas de marché en soi (Qiskit, CUDA-Q, Q#, Guppy, PennyLane occupent le terrain). Ce qui est défendable : une couche qui décrit un flux **classique + distribué + quantique**, estime les ressources de chaque étape et décide où l'exécuter — y compris « pas sur un QPU ». C'est ce que le prototype implémente.

## 6. Problèmes non résolus par les grands acteurs

1. **Utilisation des GPU d'entreprise** (5 % mesurés par Cast AI) : problème d'ordonnancement, de partage et de mémoire, pas de matériel.
2. **Coût par jeton du cache KV à étages** : personne ne publie le point d'équilibre recalcul / rechargement selon l'étage et la latence.
3. **Décision de placement multi-ressources unifiée** : ordonnanceurs GPU, étagement mémoire, routage d'inférence et choix d'environnement sont des produits séparés qui ne partagent ni modèle de coût ni mesures.
4. **Mesure honnête** : la plupart des chiffres du secteur sont des benchmarks de fournisseurs.

## Sources

- Altman : [mindstudio.ai](https://www.mindstudio.ai/blog/sam-altman-ram-comment-controversy), [Tom's Hardware](https://www.tomshardware.com/tech-industry/data-centers/openai-ceo-says-its-quite-terrible-for-your-pc-to-have-ram-sam-altman-says-data-centers-offer-better-utilization), [TechPowerUp](https://www.techpowerup.com/354346/openai-ceo-argues-home-pcs-waste-the-worlds-limited-dram-supply), [implicator.ai](https://www.implicator.ai/when-talking-about-local-inference-sam-altman-says-supply/), [cellcog.ai](https://cellcog.ai/blog/altman-dram-local-inference/)
- DRAM : [Network World](https://www.networkworld.com/article/4113772/samsung-warns-of-memory-shortages-driving-industry-wide-price-surge-in-2026.html), [Bloomberg](https://www.bloomberg.com/graphics/2026-ai-boom-memory-chip-shortage/), [nand-research.com](https://nand-research.com/memory-nand-flash-crisis-may-2026-update/), [evertiq](https://evertiq.com/news/2026-01-05-dram-and-nand-flash-prices-to-surge-in-q1-2026)
- Mémoire lointaine : [Google Research](https://research.google/pubs/software-defined-far-memory-in-warehouse-scale-computers/), [The Morning Paper](https://blog.acolyer.org/2019/05/22/sw-far-memory/), [Infiniswap NSDI'17](https://www.usenix.org/conference/nsdi17/technical-sessions/presentation/gu), [AIFM OSDI'20](https://usenix.org/conference/osdi20/presentation/ruan), [Eden NSDI'25](https://cseweb.ucsd.edu/~snoeren/papers/eden-nsdi25.pdf), [Memory Disaggregation survey](https://arxiv.org/pdf/2305.03943)
- CXL : [CXL Consortium — Vistara](https://computeexpresslink.org/?p=4700), [HPCwire](https://www.hpcwire.com/2026/08/20/what-hyperscalers-should-know-about-cxl/), [Futurum — Marvell](https://futurumgroup.com/insights/marvell-scales-ai-memory-to-48tb-behind-a-single-cxl-switch-at-fms-2026/)
- Utilisation GPU : [Cast AI](https://cast.ai/press-release/2026-state-of-kubernetes-optimization-report/), [TechRadar](https://www.techradar.com/pro/5-utilization-is-a-math-fail-millions-of-gpus-worth-billions-are-mostly-sitting-idle-report-finds), [ClearML](https://go.clear.ml/state-of-ai-infrastructure-report-25-26), [36Kr](https://eu.36kr.com/en/p/4039561205011586)
- Investissements : [Yahoo Finance](https://finance.yahoo.com/sectors/technology/articles/hyperscalers-hit-700-billion-2026-111243744.html), [resultsense](https://www.resultsense.com/news/2026-04-30-hyperscaler-ai-capex-725bn)
- Cache KV, llm-d : [docs vLLM](https://docs.vllm.ai/en/latest/deployment/integrations/llm-d.html), [llm-d.ai](https://llm-d.ai/docs/architecture/architecture), [arXiv 2511.00321](https://arxiv.org/html/2511.00321v1), [arXiv 2605.18071](https://arxiv.org/pdf/2605.18071), [Samsung CMM-D](https://download.semiconductor.samsung.com/resources/white-paper/Optimizing_KV_Cache_Offloading_to_CMM-D_in_a_CXL_Switch-based_Memory_Pool.pdf)
- Inférence distribuée : [Petals arXiv 2209.01188](https://arxiv.org/pdf/2209.01188v2.pdf), [Petals NeurIPS 2023](https://neurips.cc/virtual/2023/poster/71336), [blog Exo](https://blog.exolabs.net/day-1)
- Quantique : [alphaXiv 2604.11599](https://www.alphaxiv.org/abs/2604.11599), [arXiv 2404.14299](https://arxiv.org/pdf/2404.14299v2), [IBM newsroom](https://newsroom.ibm.com/2026-07-30-ibm-and-algorithmiq-demonstrate-quantum-advantage,-establishing-a-framework-for-trusted-quantum-computation-beyond-classical-verification), [The Next Platform](https://www.nextplatform.com/compute/2026/07/31/ibm-three-demonstrations-prove-quantum-advantage-has-been-reached/5282091), [The Quantum Insider](https://thequantuminsider.com/2026/11/06/study-maps-24-problems-where-quantum-computers-could-gain-an-edge/)

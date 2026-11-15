# 07 — Les sept domaines : état réel

Trois niveaux, repris de `spatial/core/registry.py` :
- **prototype opérationnel** : s'exécute, testé et mesuré sur ce Mac ;
- **premiers composants** : un peu de code réel et testé, pas un produit ;
- **interface seule** : modèle de données, aucune fonction.

| Domaine | Moteur | Niveau | Preuve | Explicitement non fait |
|---|---|---|---|---|
| 1 | Spatial Compute Engine (+ Resource Engine pour la mémoire) | Prototype opérationnel | `tests/test_compute.py`, `tests/test_memory.py`, `benchmarks/bench_cpu.py`, `bench_memory.py`, `bench_gpu.py` | Aucune seconde machine ; pas d'ordonnancement GPU ; pas de pagination noyau ; pas de CXL/RDMA |
| 2 | Spatial Runtime Engine | Prototype opérationnel | `tests/test_runtime.py`, `benchmarks/bench_runtime.py` | Applications Windows non exécutées ; pas d'interface graphique distante ; pas de conteneurs OCI |
| 3 | SPATIAL Q | Prototype opérationnel | `tests/test_q.py`, `benchmarks/bench_q.py` | Aucun QPU ; pas de QIR ; partie classique interprétée |
| 4 | Spatial AI Engine | Interface seule (public) | `spatial/ai/__init__.py` | Aucune inférence ; le planificateur est dans un paquet privé |
| 5 | Scientific & Industrial Engine | Premiers composants | `tests/test_domains.py` | Un seul job de référence |
| 6 | Holographic Engine | Interface seule | `tests/test_domains.py` | Aucun affichage, aucune synthèse d'hologramme |
| 7 | Simulation Engine / Intelligence Engine | Premiers composants | `tests/test_domains.py` | Un solveur jouet ; un prédicteur par moindres carrés |

## Domaine 1 — Universal Computing Architecture

Fonctions du brief et couverture :

| # | Fonction | État |
|---|---|---|
| 1 | Détection du matériel | Fait (`compute/detect.py`) |
| 2 | Surveillance des ressources | Fait (`compute/monitor.py`) : CPU, RAM, swap, compresseur, pression |
| 3 | Ressources sous-utilisées | Fait, simple (`monitor.underused`) |
| 4 | Calcul distribué | Fait sur boucle locale (worker SWP/0) ; non validé entre deux machines |
| 5 | Orchestration GPU | Mesure locale seulement (Metal) ; pas d'orchestration |
| 6 | Orchestration CPU | Fait : comparaison de stratégies, pool de processus, threads |
| 7 | Optimisation mémoire | Fait : compression, déduplication |
| 8-9 | Mutualisation et mémoire distribuée | Prototype applicatif : serveur de pages distant ; un seul écrivain |
| 10 | Optimisation du stockage | Étage SSD du magasin à étages seulement |
| 11 | Optimisation réseau | Lecture anticipée groupée, copies propres ; rien d'autre |
| 12 | Optimisation des coûts | Modèle de coût (`compute/cost.py`) ; prix cloud non vérifiés |
| 13 | Ordonnancement | Choix de stratégie par objectif ; pas de file d'attente multi-tâches |
| 14 | Intégration cloud | Non fait (aucun compte) |
| 15 | Place de marché | Non fait ; déconseillé en phase 1 |

## Domaine 2 — Universal Software Runtime

| # | Fonction | État |
|---|---|---|
| 1-2 | Runtime universel, compatibilité multiplateforme | Routes implémentées : natif, micro-VM Linux (HVF et TCG), WASM/WASI, interpréteur. Wine : route décrite, non exécutable ici |
| 3, 11 | Exécution distante / cloud | Non fait |
| 4 | Détection d'environnement | Fait (`runtime/envs.py`, `planner.host_caps`) |
| 5 | Gestion des dépendances | Environnements Python isolés (uv) |
| 6 | Traduction de runtime | Émulation TCG mesurée ; pas de traduction binaire propre |
| 7 | Isolation | Micro-VM sans réseau ni disque ; bac à sable WASI |
| 8 | Environnements virtuels | Création/destruction automatisées |
| 9 | Bureau distant | Non fait |
| 10 | Exécution selon le matériel | Le planificateur lit les capacités de l'hôte |
| 12 | Sécurité et permissions | Partiel (voir architecture §7) |

Exemple du brief (logiciel Windows sur Mac) : le moteur **identifie** le binaire PE et **explique** pourquoi aucune route n'est disponible sur cette machine (pas de Wine, pas d'image Windows, pas d'hôte distant). Il ne l'exécute pas. Pour le démontrer : installer Wine/CrossOver (accord de l'utilisateur requis) ou fournir une image Windows sous licence.

## Domaine 3 — SPATIAL Q

Voir `06_SPATIAL_Q_SPEC.md`. Les six couches du brief :

| Couche | État |
|---|---|
| Langage | Spécifié, grammaire EBNF |
| Compilateur | Lexer, parser, spécialisation, optimiseur |
| Représentation intermédiaire | SQIR (JSON) + export OpenQASM 3 |
| Runtime | Interpréteur + trace des décisions |
| Orchestrateur | Choix de backend par estimation de ressources ; tâches cpu/worker/any |
| Backends | NumPy, Qiskit Aer, export QASM 3 ; QPU non connecté |

## Domaine 4 — Advanced AI Computing Infrastructure

Dans ce dépôt public : interface seule. Le planificateur analytique de placement d'un modèle sur des nœuds hétérogènes est développé dans un paquet privé (`spatial_pro`) ; `spatial.ai` le ré-exporte s'il est installé. Aucune inférence de modèle n'est exécutée ici. À construire : routage de modèles, étagement du cache KV, intégration vLLM/llm-d, mesures sur GPU réels.

## Domaine 5 — Scientific & Industrial Computing

Composant existant : `spatial/scientific/jobs.py`. Un `JobSpec` associe un calcul à une valeur de référence indépendante ; le moteur l'exécute, le mesure et **échoue** si le résultat s'écarte de plus de quelques écarts-types. Job fourni : prix d'une option européenne par Monte-Carlo, validé par la formule de Black-Scholes.

Besoins sectoriels (connaissance générale, non issue d'entretiens clients) :

| Secteur | Charges dominantes | Moteurs concernés |
|---|---|---|
| Pharma, biotech, chimie, matériaux | Dynamique moléculaire, docking, DFT ; à terme simulation quantique | Compute, mémoire à étages, SPATIAL Q |
| Aéronautique, automobile, énergie | CFD, éléments finis, jumeaux numériques | Compute, Simulation |
| Finance quantitative | Monte-Carlo, risque, backtests | Compute (lots, déport) |
| Logistique | Optimisation combinatoire | Compute ; quantique non démontré utile |
| Défense | Contraintes de souveraineté et d'isolation | Runtime (isolation), déploiement privé |

## Domaine 6 — Physical & Holographic Computing

Interface seule : `VoxelGrid`, `voxelize` (nuage de points → grille d'occupation) et `LightFieldSpec`, qui calcule le débit de pixels d'un écran à champ lumineux. Exemple testé : 45 vues de 1536 × 2048 à 60 Hz représentent environ 17 écrans 4K en débit de pixels. Ce calcul fixe l'exigence de rendu que le Compute Engine devrait servir.

Rappel de terminologie : un écran à champ lumineux ou volumétrique n'est pas un hologramme au sens physique (reconstruction de front d'onde par diffraction, qui demande des modulateurs à pas sub-micrométrique). L'ambition d'affichage holographique physique est conservée comme horizon ; rien n'a été construit ni simulé.

## Domaine 7 — Computing Intelligence & Simulation

- **Simulation** (`spatial/simulation/heat.py`) : diffusion de chaleur 2D explicite, variantes NumPy et Numba donnant le même champ, condition de stabilité vérifiée, conservation de la chaleur testée.
- **Intelligence** (`spatial/intelligence/predictor.py`) : loi de puissance durée ≈ a·travailᵇ ajustée par stratégie à partir du registre de mesures ; permet d'estimer une durée avant d'exécuter.

À construire : multiphysique, simulation robotique, modèles du monde. Ces sujets relèvent de la recherche et de moyens de calcul sans rapport avec ce prototype.

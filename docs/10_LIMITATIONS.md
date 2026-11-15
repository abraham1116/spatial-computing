# 10 — Limitations

## Matériel

| Limite | Conséquence | Ce qu'il faudrait |
|---|---|---|
| Une seule machine | Déport et distribution validés en boucle locale seulement ; aucun gain de capacité démontré | Un second ordinateur sur le même réseau, puis un serveur distant |
| 2 cœurs physiques | Parallélisme plafonné à ~2× | Station ou serveur multi-cœurs |
| GPU intégré Intel, sans float64, sans CUDA | Un seul noyau de calcul mesuré ; aucune inférence | GPU Nvidia de centre de données (location) |
| Pas de CXL, RDMA, NVMe-oF | Étudiés sur documents uniquement | Serveurs récents avec cartes adaptées |
| Pas de QPU | SPATIAL Q testé en simulation uniquement | Compte chez un fournisseur |
| Processeur Intel | Pas de MLX ni de Neural Engine ; invités ARM en émulation lente | Mac Apple Silicon pour ces tests |

## Mesure

- **Énergie non mesurée.** La jauge de batterie est restée à 32,5 W pendant 24 s entre repos et pleine charge. Les coûts énergétiques du rapport sont des estimations à partir de cette seule lecture. Il faut `powermetrics` (root) ou un wattmètre.
- **Alimentation.** Sur batterie faible, les mêmes tests étaient environ trois fois plus lents. Les chiffres publiés sont sur secteur.
- **Liens réseau émulés.** Délais ajoutés par `sleep`, qui dépasse sa consigne ; ce ne sont pas des mesures de réseau.
- **Peu de répétitions** (1 à 5), pas d'intervalle de confiance, charge de fond non contrôlée (éditeur, navigateur ouverts).
- **Référence CPU du test GPU scalaire** : l'écart GPU/CPU serait plus faible face à du code vectorisé.
- **Prix cloud** cités de mémoire, non revérifiés ; rapports de vitesse cloud/local supposés.

## Logiciel

| Composant | Limite |
|---|---|
| Mémoire à étages | Bibliothèque en Python utilisée par API ; pas de pagination transparente ; un seul écrivain ; pas de chiffrement ni de réplication des pages lointaines ; latences dominées par l'interpréteur |
| Protocole SWP/0 | Canal non chiffré ; une requête à la fois par connexion ; entête JSON |
| Worker | Liste blanche de charges de démonstration ; pas de charges arbitraires |
| Ordonnanceur | Compare en exécutant tout ; pas de file d'attente, pas de priorités ; une famille de charges |
| Runtime | Windows non exécuté (ni Wine ni image) ; pas de conteneurs ; pas d'interface graphique ; micro-VM sans réseau ni fichiers partagés, donc limitée à des programmes autonomes statiques |
| SPATIAL Q | Partie classique interprétée ; pas de sous-noyaux ni de portes utilisateur ; pas de QIR ; simulateur exact limité à ~27 qubits sur cette machine ; optimiseur à trois règles |
| Domaines 4 à 7 | Voir `07_SEPT_DOMAINES.md` |

## Recherche

- Pas de recherche de brevets.
- Plusieurs chiffres de marché viennent de sources secondaires ; les financements de Vast.ai, Salad, io.net, Akash, Golem, Exo n'ont pas pu être sourcés.
- La citation d'Altman est rapportée par la presse ; pas de transcription vérifiée.
- Aucun entretien client.
- Aucun skill de stratégie de startup n'était installé.

## Environnement

- Le dossier du projet se termine par une espace (`SPATIAL COMPUTING `) : à renommer avant publication.
- La protection d'intégrité du système (SIP) était déjà en configuration personnalisée avant la session.

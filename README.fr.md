# Spatial Computing

**Mesurer. Décider. Prouver.**

Spatial Computing choisit où et comment exécuter une charge de travail à partir de mesures, et ne revendique un gain que s'il est mesuré. Il n'ajoute ni RAM, ni cœurs, ni GPU : il compare des stratégies d'exécution sur le matériel présent, échange une ressource contre une autre de façon chiffrée, et dit clairement ce qu'il ne sait pas faire.

> **Statut : v0.15.0, boîte à outils open source à un stade précoce.** Tout a été construit et mesuré sur un seul MacBook Pro 2017 (Intel i7-7660U, 2 cœurs, 16 Go). Rien n'est prouvé sur une seconde machine, un GPU de centre de données ou un vrai ordinateur quantique. Voir [Limitations](docs/10_LIMITATIONS.md).

[English](README.md)

## Installation

Python 3.10 ou plus. Pas encore sur PyPI : installation depuis les sources.

```bash
git clone https://github.com/abraham1116/spatial-computing && cd spatial-computing
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[quantum,dev]"
spatial audit
pytest
```

## Console (comptes, apps, clés d'API, jobs, facturation)
```bash
spatial token init --master-key-file hub.key
spatial serve hub --master-key-file hub.key --port 7700 --usage-file usage.jsonl --revoked-file revoked.txt
spatial platform serve --master-key-file hub.key --hub 127.0.0.1:7700 --usage-file usage.jsonl --revoked-file revoked.txt
# ouvrir http://127.0.0.1:8090/ : créer un compte, une app, une clé nœud et une clé client
spatial agent --hub 127.0.0.1:7700 --token-file node.tok     # la machine apparaît dans Fleet ; soumettre des jobs depuis Jobs
```
Production (hub, console, HTTPS) : `docker compose --env-file deploy/.env up -d --build`. Voir [docs/PLATFORM.md](docs/PLATFORM.md) et [docs/DEPLOY.md](docs/DEPLOY.md).

## Utilisation

```bash
spatial audit        # matériel, usage, limites de cette machine
spatial status       # état réel de chaque moteur
spatial plan app.exe # format détecté + routes d'exécution avec raisons
spatial run app.elf  # exécution par la première route réalisable
spatial q run examples/03_vqe_hybrid.sq --trace
spatial bench all    # refait les mesures et régénère le tableau
```

## Ce que Spatial ne fait pas

- Il n'ajoute pas de RAM : la mémoire compressée, sur disque ou distante est typée `far_memory`, jamais `ram`.
- Il ne confond pas virtualisation et ressource supplémentaire.
- Il ne prétend pas qu'un QPU accélère quoi que ce soit : tout SPATIAL Q est de la simulation classique.
- Il n'expose jamais la machine : les serveurs écoutent sur `127.0.0.1` sauf `--allow-remote` explicite.

## Open-core

Le cœur de ce dépôt est sous licence [Apache-2.0](LICENSE). Les politiques avancées de placement et de coût sont développées dans un paquet privé séparé.

Documentation complète : <https://spatial-computing-ecru.vercel.app> (anglais et français). Rapports techniques dans [`docs/`](docs/) (en français).

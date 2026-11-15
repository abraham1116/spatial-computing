"""Builds docs/RESULTATS.md from benchmarks/results/*.json. Numbers are copied from the
JSON files; nothing is typed by hand except the commentary and the stated assumptions."""
from __future__ import annotations

import json

from common import RESULTS, ROOT
from spatial.compute.cost import CostModel
from spatial.core.registry import table as engine_table


def load(name):
    p = RESULTS / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def f(x, nd=3):
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "oui" if x else "non"
    if isinstance(x, (int,)):
        return f"{x:,}".replace(",", " ")
    ax = abs(x)
    if ax >= 1000:
        return f"{x:,.0f}".replace(",", " ")
    if ax >= 100:
        return f"{x:.0f}"
    if ax >= 10:
        return f"{x:.1f}"
    if ax >= 1:
        return f"{x:.2f}"
    return f"{x:.{nd}g}"


def ctx_line(d):
    c = d["context"]
    return (f"*Mesuré le {c['date']} — {c['model']}, {c['cpu']}, {c['os']} — {c['power_source']} "
            f"({c['battery']}).*")


def main():
    L = ["# Résultats mesurés", "",
         "Ce fichier est généré par `benchmarks/report.py` à partir des fichiers JSON de "
         "`benchmarks/results/`. Pour refaire les mesures : voir `README.md`. Les chiffres changent d'une "
         "exécution à l'autre (charge de fond, température, alimentation).", ""]

    # ------------------------------------------------------------------ CPU
    cpu = load("cpu")
    if cpu:
        L += ["## Test 2 — CPU : local, optimisé, parallèle, distribué, distant", "", ctx_line(cpu), "",
              "Problème : la même somme de contrôle Mandelbrot calculée par chaque stratégie ; une stratégie "
              "ne compte que si son résultat est identique à la référence. La compilation JIT est faite avant "
              f"le chronométrage (durée : {f(cpu['jit_warmup_s'])} s, pool de processus inclus). "
              "« Distant » et « distribué » utilisent un worker qui est **un processus sur ce même Mac** "
              "(boucle locale) : ils mesurent le surcoût du protocole, pas l'apport d'une seconde machine. "
              "La colonne CPU ne compte que le processus appelant et ses enfants terminés : elle **exclut** le worker "
              "et le pool persistant, d'où des valeurs proches de zéro sur ces lignes.", ""]
        by = {e["name"]: e for e in cpu["experiments"]}
        slow = by.get("mandel_small_slow_references")
        py = next((r["wall_s"] for r in slow["rows"] if r["strategy"] == "local_python"), None) if slow else None
        for name in ("mandel_small_slow_references", "mandel_small_fast_strategies", "mandel_large_fast_strategies"):
            e = by.get(name)
            if not e:
                continue
            p = e["params"]
            L += [f"### {name} — n = {p['n']}, itérations = {p['iters']}, {e['repeat']} répétition(s), médiane", "",
                  "| Stratégie | Type | Durée (s) | CPU (s) | CPU/durée | Accélération vs Python pur | Résultat identique |",
                  "|---|---|---|---|---|---|---|"]
            for r in e["rows"]:
                if not r.get("ok"):
                    L.append(f"| {r['strategy']} | — | échec : {r.get('notes')} | | | | |")
                    continue
                sp = py / r["wall_s"] if (py and p["n"] == 700) else None
                L.append(f"| {r['strategy']} | {r['kind']} | {f(r['wall_s'])} | {f(r['cpu_s'])} | "
                         f"{f(r['cpu_utilisation'])} | {f(sp) + '×' if sp else '—'} | {f(r['matches_reference'])} |")
            L.append("")
        big = by.get("mandel_large_fast_strategies")
        if big:
            rr = {r["strategy"]: r for r in big["rows"] if r.get("ok")}
            j, t = rr["local_numba_jit"]["wall_s"], rr["local_numba_threads"]["wall_s"]
            L += ["Lecture :", "",
                  f"- Compilation JIT : de l'ordre de {f(py / by['mandel_small_fast_strategies']['rows'][0]['wall_s'])}× "
                  "sur Python pur. C'est le gain dominant, et il est purement logiciel.",
                  f"- Deux cœurs : {f(j / t)}× sur le grand cas — la limite matérielle attendue.",
                  f"- Pool de processus à froid : {f(rr['multiprocess_numba']['wall_s'])} s contre "
                  f"{f(rr['multiprocess_warm_pool']['wall_s'])} s à chaud. Le démarrage des processus et l'import "
                  "des bibliothèques coûtent plus d'une seconde ; d'où le pool persistant (optimisation de l'étape 7).",
                  f"- Worker en boucle locale : {f(rr['remote_worker']['wall_s'])} s contre {f(j)} s en local sur un fil — "
                  "le protocole n'ajoute rien de mesurable à cette échelle. « Distribué » "
                  f"({f(rr['distributed_local+worker']['wall_s'])} s) égale les threads parce que le worker occupe le second cœur "
                  "de la même machine. **Aucun gain de capacité n'a été démontré** : il faudrait un second ordinateur.",
                  "- Énergie : non mesurée (voir Limitations).", ""]
        L += ["**Effet de l'alimentation (observation).** Une première exécution de ce même benchmark a été faite "
              "sur batterie entre 20 % et 11 % de charge ; son fichier JSON a été écrasé par l'exécution ci-dessus, "
              "les valeurs viennent du journal de console : Python pur 14,15 s, NumPy 6,27 s (n = 700) ; Numba un fil "
              "11,68 s, Numba threads 5,88 s (n = 4000). Soit environ 2,8 à 3,6 fois plus lent que sur secteur. "
              "Le bridage du processeur sur batterie faible domine tous les autres effets : tout benchmark sur "
              "portable doit noter l'alimentation.", ""]

    # ------------------------------------------------------------------ GPU
    gpu = load("gpu")
    if gpu:
        L += ["## Test 3 — GPU local (Metal) contre CPU", "", ctx_line(gpu), "",
              "Même calcul en float32 des deux côtés (le GPU intégré n'a pas de float64). Le noyau GPU est un "
              "compute shader Metal compilé à l'exécution ; la référence CPU est Numba multi-fils. "
              "Les arrondis diffèrent (contraction FMA) : les sommes de contrôle sont comparées en écart relatif.", ""]
        if gpu.get("error"):
            L += [f"Échec : `{gpu['error'][:300]}`", ""]
        else:
            L += ["| n | Itérations | CPU Numba threads (s) | GPU Metal (s) | GPU / CPU | Écart relatif des sommes |", "|---|---|---|---|---|---|"]
            for r in gpu["rows"]:
                L.append(f"| {r['n']} | {r['iters']} | {f(r['cpu_numba_threads_f32_s'])} | {f(r.get('gpu_s'))} | "
                         f"{f(r.get('gpu_speedup_vs_cpu'))}× | {f(r.get('checksum_rel_diff'))} |")
            g0 = gpu["rows"][0].get("gpu", {})
            L += ["", f"Périphérique : {g0.get('device')}. Compilation du shader et création du pipeline : "
                  f"{f(g0.get('setup_s'))} s (hors chronométrage). Compilation Swift : {f(gpu['swift_build_s'])} s.", "",
                  "Lecture : sur cette charge massivement parallèle, le GPU intégré est 20 à 30 fois plus rapide que "
                  "les deux cœurs. **Réserve importante** : la référence CPU est scalaire (Numba ne vectorise pas cette "
                  "boucle à sortie anticipée) ; une version AVX2 écrite à la main réduirait l'écart, d'un facteur non mesuré. "
                  "Ce résultat ne se généralise pas : pas de float64, 1,5 Go de mémoire partagée, aucune pile "
                  "d'inférence sérieuse ne cible ce GPU.", "",
                  f"GPU distant : {gpu['remote_gpu']}.", ""]

    # ------------------------------------------------------------------ memory
    mem = load("memory")
    if mem:
        sm = mem["system_memory"]
        L += ["## Test 1 — Mémoire", "", ctx_line(mem), "",
              "### A. État réel de la mémoire du Mac", "",
              "| Grandeur | Valeur |", "|---|---|",
              f"| RAM totale | {f(sm['ram_total'] / 2**30)} Gio |",
              f"| RAM disponible | {f(sm['ram_available'] / 2**30)} Gio |",
              f"| Swap utilisé | {f(sm['swap_used'] / 2**30)} / {f(sm['swap_total'] / 2**30)} Gio |",
              f"| Pages tenues par le compresseur (taille logique) | {f(sm['compressor_logical_bytes'] / 2**30)} Gio |",
              f"| RAM occupée par le compresseur | {f(sm['compressor_physical_bytes'] / 2**30)} Gio |",
              f"| Taux de compression du système | {f(sm['compressor_ratio'])} |",
              f"| Pression mémoire | {sm['memory_pressure']} |", "",
              "macOS compresse déjà la mémoire froide : c'est la référence à battre, et elle est gratuite.", "",
              "### B. Codecs selon le contenu (pages de 64 Kio)", "",
              "| Contenu | Codec | Taux | Compression (Mo/s) | Décompression (Mo/s) |", "|---|---|---|---|---|"]
        for r in mem["codecs"]:
            L.append(f"| {r['content']} | {r['codec']} | {f(r['ratio'])} | {f(r['compress_MBps'])} | {f(r['decompress_MBps'])} |")
        L += ["", "Le contenu décide de tout : des données aléatoires (ou déjà compressées, ou chiffrées) ne gagnent rien.", "",
              "### C. Magasin à étages : latence d'accès par configuration", "",
              "Jeu de données : pages de 64 Kio, 40 % numériques, 40 % texte, 20 % aléatoires. Chaque configuration "
              "tourne dans un processus neuf. « LAN émulé » et « WAN émulé » ajoutent un délai et un plafond de débit "
              "artificiels à un serveur de pages en boucle locale : **ce sont des émulations**, pas des mesures de réseau réel "
              "(et `sleep` dépasse sa consigne de quelques dizaines à centaines de microsecondes, ce qui les pessimise).", "",
              "| Configuration | Accès | Logique (Mo) | RAM locale (Mo) | RSS pic (Mo) | Moyenne (µs/accès) | Chaud | Compressé | Lointain | p50 / p99 compressé (µs) | p50 / p99 lointain (µs) | CPU (s) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in mem["tiered"]:
            c = r["config"]
            L.append(f"| {c['label']} | {c['pattern']} | {f(r['logical_MB'])} | {f(r['local_ram_MB'])} | {f(r['peak_rss_MB'])} | "
                     f"{f(r['mean_access_us'])} | {f(r['hot_hit_ratio'])} | {f(r['compressed_hit_ratio'])} | {f(r['far_hit_ratio'])} | "
                     f"{f(r.get('compressed_p50_us'))} / {f(r.get('compressed_p99_us'))} | "
                     f"{f(r.get('far_p50_us'))} / {f(r.get('far_p99_us'))} | {f(r['cpu_s'])} |")
        rows = {r["config"]["label"]: r for r in mem["tiered"]}
        base = rows["baseline all-in-RAM"]
        ssd = rows["tiered + SSD file"]
        s0 = rows["sequential scan LAN, no read-ahead"]
        s1 = rows["sequential scan LAN, read-ahead 16"]
        s2 = rows.get("sequential scan LAN, read-ahead 16 + clean-copy retention")
        L += ["", "Lecture :", "",
              f"- Tout en RAM : {f(base['mean_access_us'])} µs par accès. Avec étages et SSD : {f(ssd['mean_access_us'])} µs en moyenne, "
              f"soit environ {f(ssd['mean_access_us'] / base['mean_access_us'])} fois plus lent, pour {f(ssd['local_ram_MB'])} Mo de RAM locale au lieu de "
              f"{f(base['local_ram_MB'])} Mo ({f(100 * (1 - ssd['local_ram_MB'] / base['local_ram_MB']))} % de moins). "
              "C'est un échange, pas un gain : la mémoire économisée se paie en latence et en CPU.",
              "- La RSS du processus baisse moins que la comptabilité interne (surcoût de l'interpréteur Python et des tampons).",
              "- Accès uniforme : la majorité des accès tombent hors de l'étage chaud ; l'étagement n'a alors pas d'intérêt.",
              "- Lien lent émulé à 20 ms : plus de dix millisecondes par accès en moyenne. Inutilisable pour autre chose que des données froides.",
              f"- Boucle d'optimisation sur le balayage séquentiel (LAN émulé) : {f(s0['mean_access_us'])} µs sans lecture anticipée → "
              f"{f(s1['mean_access_us'])} µs avec lecture anticipée de 16 pages"
              + (f" → {f(s2['mean_access_us'])} µs en conservant en plus la copie lointaine des pages non modifiées "
                 f"(×{f(s0['mean_access_us'] / s2['mean_access_us'])} au total)." if s2 else "."),
              "- **Aucune de ces configurations n'ajoute de RAM.** Elles permettent d'adresser plus de données que le budget de RAM locale, plus lentement.", ""]

    # ------------------------------------------------------------------ runtime
    rt = load("runtime")
    if rt:
        L += ["## Test 4 — Runtime logiciel", "", ctx_line(rt), "",
              "Un même programme C compilé pour quatre cibles ; le moteur inspecte chaque binaire, choisit une route et l'exécute. "
              f"La somme imprimée doit valoir {rt['reference_checksum']} partout (n = {rt['params']['n']}, itérations = {rt['params']['iters']}).", "",
              "| Binaire | Format détecté | Routes envisagées (réalisable ?) |", "|---|---|---|"]
        for a in rt["artifacts"]:
            routes = " ; ".join(f"{r['name']} ({'oui' if r['feasible'] else 'non'})" for r in a["routes"])
            L.append(f"| {a['file']} ({f(a['bytes'] / 1024)} Kio) | {a['format']} / {a['os']} / {','.join(a['arch'])} | {routes} |")
        L += ["", "| Cible | Route | OK | Calcul dans l'application (ms) | Durée totale (s) | Démarrage (s) | Ralentissement vs natif | Somme correcte |",
              "|---|---|---|---|---|---|---|---|"]
        for r in rt["runs"]:
            if r["ok"]:
                L.append(f"| {r['target']} | {r['route']} | oui | {f(r['app_ms'])} | {f(r['total_wall_s'])} | {f(r['startup_overhead_s'])} | "
                         f"{f(r['slowdown_vs_native'])}× | {f(r['checksum_ok'])} |")
            else:
                L.append(f"| {r['target']} | aucune | **non** | — | — | — | — | — |")
        win = next((r for r in rt["runs"] if not r["ok"]), None)
        ie = rt["isolated_env"]
        L += ["", "Lecture :", "",
              "- Micro-VM Linux avec virtualisation matérielle (HVF) : calcul à quelques pour cent du natif, moins d'une seconde de démarrage, aucun réseau ni disque exposé.",
              "- Même binaire en émulation logicielle (TCG) : plus de vingt fois plus lent. C'est le coût à attendre pour exécuter un autre jeu d'instructions (ARM sur ce Mac Intel).",
              "- WASM sous Node/WASI : environ une fois et demie le temps natif, sans machine virtuelle.",
              f"- Binaire Windows : **non exécuté**. Raison rapportée par le moteur : {win['not_runnable'] if win else '—'}.",
              f"- Environnement Python isolé avec une dépendance épinglée : créé en {f(ie['create_and_install_s'])} s.",
              "- Comparaison avec Docker Desktop, UTM, Parallels, CrossOver : non faite, aucun n'est installé.", ""]

    # ------------------------------------------------------------------ Q
    q = load("spatialq")
    if q:
        L += ["## Test 5 — SPATIAL Q", "", ctx_line(q), "",
              "Tout ce qui suit est de la **simulation classique** de circuits quantiques. Aucun QPU n'a été utilisé ; aucune accélération quantique n'est mesurée.", "",
              "### Simulateur intégré contre Qiskit (mêmes circuits, 1000 tirs)", "",
              "| Qubits | Portes | Compilation (s) | Vecteur d'état (Mo) | SPATIAL Q NumPy (s) | Qiskit Aer (s) | SPATIAL Q / Aer | Fidélité vs Qiskit |",
              "|---|---|---|---|---|---|---|---|"]
        for r in q["scaling"]:
            fid = f"{r['fidelity_vs_qiskit']:.12f}" if "fidelity_vs_qiskit" in r else "non calculée"
            L.append(f"| {r['qubits']} | {r['ops']} | {f(r['compile_s'])} | {f(r['statevector_MB'])} | {f(r['spatialq_numpy_s'])} | "
                     f"{f(r['aer_s'])} | {f(r['ratio_spatialq_over_aer'])} | {fid} |")
        d, v = q["dynamic"], q["vqe"]
        L += ["", f"Avec {f(q['ram_available_GB'])} Go disponibles au moment du test, la limite de simulation exacte sur ce Mac est d'environ "
              f"**{q['max_qubits_exact_here']} qubits** (16 × 2ⁿ octets, en gardant la moitié de la RAM libre).", "",
              "Lecture : résultats numériquement identiques à Qiskit. Le simulateur NumPy est plus rapide qu'Aer sous 12 qubits "
              "(Aer a un coût fixe de lancement) et 6 à 8 fois plus lent à 20-22 qubits. Pour des circuits sérieux, le backend `aer` est le bon choix ; "
              "le simulateur intégré sert de référence indépendante.", "",
              "### Optimiseur", "", "| Noyau | Portes avant | Portes après | Passes | Compilation (s) |", "|---|---|---|---|---|"]
        for o in q["optimizer"]:
            L.append(f"| {o['kernel']} | {o['ops_before']} | {o['ops_after']} | {o['passes']} | {f(o['compile_s'])} |")
        L += ["", "Ce cas (QFT suivie de son inverse) est construit pour s'annuler entièrement ; il vérifie l'optimiseur, il ne dit rien de son efficacité sur des circuits réels.", "",
              "### Circuits dynamiques (téléportation, 4000 tirs)", "",
              "| Méthode | Durée (s) |", "|---|---|",
              f"| Simulation tir par tir (première version) | {f(d['per_shot_s'])} |",
              f"| Énumération des branches de mesure (après optimisation) | {f(d['branch_enumeration_s'])} |",
              f"| Qiskit Aer | {f(d['aer_s'])} |", "",
              f"Gain de l'optimisation : ×{f(d['speedup_branch_vs_per_shot'])}. Probabilité mesurée que le qubit téléporté vaille 1 : "
              f"{f(d['p_q2_is_1'])} ; attendue : {f(d['expected'])}.", "",
              "### Programme hybride (VQE)", "",
              f"Énergie trouvée : {v['energy']:.9f} ; diagonalisation exacte : {v['exact']:.9f} ; écart : {v['abs_error']:.1e}. "
              f"{v['quantum_evaluations']} évaluations de noyau quantique pilotées par la boucle classique, en {f(v['wall_s'])} s.", ""]

    # ------------------------------------------------------------------ costs
    L += ["## Test 6 — Coûts", "",
          "**Aucun coût n'a été mesuré directement.** L'énergie n'a pas pu l'être (jauge de batterie figée, voir Limitations) et aucune ressource "
          "cloud n'a été louée. Le tableau applique le modèle de `spatial/compute/cost.py` aux durées mesurées, avec des hypothèses explicites.", "",
          "Hypothèses : électricité 0,17 $/kWh ; puissance de la machine entière 32,5 W (seule lecture de jauge obtenue, sur batterie) ; "
          "prix à la demande AWS de mémoire, **non revérifiés** (c7i.large 0,0893 $/h, c7i.4xlarge 0,714 $/h) ; facturation minimale de 60 s ; "
          "rapports de vitesse cloud/local supposés (1,5× pour 2 vCPU récents, 12× pour 16 vCPU) ; portable à 1500 $ amorti sur 4 ans à 8 h/jour (hypothèse).", ""]
    if cpu:
        cm = CostModel()
        big = next(e for e in cpu["experiments"] if e["name"] == "mandel_large_fast_strategies")
        best = min((r for r in big["rows"] if r.get("ok")), key=lambda r: r["wall_s"])
        w = best["wall_s"]
        e_usd = 32.5 * w / 3.6e6 * cm.usd_per_kwh
        amort = 1500 / (4 * 365 * 8) * w / 3600
        L += [f"Charge : grand cas du test 2, meilleure stratégie locale ({best['strategy']}, {f(w)} s mesurées).", "",
              "| Option | Durée | Coût par exécution | Nature |", "|---|---|---|---|",
              f"| Local, matériel déjà payé | {f(w)} s (mesuré) | {e_usd:.2e} $ d'électricité | durée mesurée, énergie estimée |",
              f"| Local, matériel amorti | {f(w)} s (mesuré) | {e_usd + amort:.2e} $ | estimation |"]
        for k, c in big["cloud_estimates_for_fastest"].items():
            L.append(f"| {c['offer']} | {f(c['run_s'])} s (supposé) | {c['total_usd']:.2e} $ (facturé {f(c['billed_s'])} s) | estimation |")
        loc_h = 32.5 / 1000 * cm.usd_per_kwh
        L += ["", "Coût horaire en charge continue (estimations) :", "",
              "| Option | $/h | $/h ramené à la capacité locale |", "|---|---|---|",
              f"| Local, électricité seule | {loc_h:.4f} | {loc_h:.4f} |",
              f"| Local, électricité + amortissement | {loc_h + 1500 / (4 * 365 * 8):.4f} | {loc_h + 1500 / (4 * 365 * 8):.4f} |",
              f"| AWS c7i.large (supposé 1,5× plus rapide) | 0.0893 | {0.0893 / 1.5:.4f} |",
              f"| AWS c7i.4xlarge (supposé 12× plus rapide) | 0.7140 | {0.714 / 12:.4f} |", "",
              "Lecture :", "",
              "- Pour un travail de quelques secondes, le cloud coûte des centaines de fois plus cher que le local, uniquement à cause de la facturation minimale et sans compter le temps de démarrage d'instance.",
              "- En charge continue, l'électricité locale est environ dix fois moins chère que l'instance cloud équivalente **si le matériel est déjà payé**. Si l'on compte l'amortissement d'un portable acheté pour cela, le cloud redevient moins cher par unité de travail.",
              "- Donc : utiliser d'abord ce qu'on possède déjà et qui est inactif ; ne louer qu'au-delà. C'est une conclusion d'utilisation, pas de technologie.",
              "- Mémoire : l'étagement économise de la RAM locale au prix de latence ; sa valeur en dollars dépend du prix de la DRAM et du coût de la latence pour l'application — non chiffré ici.",
              "- Réseau : aucun transfert réel ; coût de sortie cloud non applicable aux tests.",
              "- QPU : aucun tarif recherché ni mesuré.", "",
              "**La question du brief — obtient-on plus de capacité pour moins cher ? — n'est pas tranchée par ces tests.** "
              "Ce qui est établi : un facteur de l'ordre de 30 à 60 obtenu en choisissant la bonne stratégie logicielle sur le même matériel, "
              "et un échange mémoire contre latence quantifié. Ce qui ne l'est pas : tout gain venant de ressources distantes.", ""]

    # ------------------------------------------------------------------ status
    L += ["## Statut des moteurs", "", engine_table(), ""]
    out = ROOT / "docs" / "RESULTATS.md"
    out.write_text("\n".join(L))
    print("written", out, len(L), "lines")


if __name__ == "__main__":
    main()

# 06 — SPATIAL Q : spécification v0.1

SPATIAL Q décrit dans un même programme du calcul classique, du calcul déporté et des circuits quantiques, et laisse un orchestrateur décider où chaque partie s'exécute à partir d'une estimation de ressources. Ce n'est pas un concurrent de Qiskit ou de CUDA-Q pour écrire des circuits : c'est une couche de flux hybride qui s'appuie sur eux (OpenQASM 3 en sortie, Qiskit Aer comme backend).

Statut : prototype exécutable. 15 tests, comparaison numérique avec Qiskit. Aucun QPU réel n'a été utilisé.

## 1. Structure d'un programme

Trois sortes de déclarations, dans n'importe quel ordre, et exactement un bloc `main`.

```
quantum bell() {                    // noyau quantique
    qubit q[2];
    h q[0];
    cx q[0], q[1];
}

task heavy(n: int) on any {         // tâche classique, cible : cpu | worker | any
    return workload("mandel_numba", n = n, iters = 200);
}

main {                              // orchestration classique
    let counts = sample bell() shots 2000;
    let zz = expect "ZZ" of bell();
    parallel { let a = heavy(400); let b = heavy(800); }
    print counts, zz, a + b;
}
```

## 2. Lexique

- Commentaires : `//` jusqu'à la fin de ligne.
- Nombres : entiers `42`, flottants `1.5`, `2e-3`. `0..n` est un intervalle, pas un flottant.
- Chaînes : `"..."` sur une ligne.
- Mots réservés : `quantum task main on qubit let for in while if else return print parallel measure reset sample shots expect of workload true false and or not`.
- Constantes : `pi`, `tau`, `e`. Fonctions : `sin cos sqrt abs min max floor acos asin exp log len float int pow`.

## 3. Grammaire (EBNF)

```
program   = { kernel | task | main } ;
kernel    = "quantum" IDENT "(" [ params ] ")" block ;
task      = "task" IDENT "(" [ params ] ")" [ "on" IDENT ] block ;
main      = "main" block ;
params    = param { "," param } ;
param     = IDENT [ ":" IDENT ] ;                 (* annotation de type : informative en v0 *)
block     = "{" { stmt } "}" ;

stmt      = "qubit" IDENT "[" expr "]" ";"        (* noyau uniquement *)
          | GATE [ "(" expr { "," expr } ")" ] qarg { "," qarg } ";"   (* noyau uniquement *)
          | "reset" qarg ";"                      (* noyau uniquement *)
          | "let" IDENT "=" expr ";"
          | IDENT "=" expr ";"
          | "for" IDENT "in" expr ".." expr block
          | "while" expr block
          | "if" expr block [ "else" block ]
          | "return" expr ";"
          | "print" expr { "," expr } ";"
          | "parallel" block                      (* hors noyau ; ne contient que des let/affectations *)
          | expr ";" ;
qarg      = IDENT [ "[" expr "]" ] ;

expr      = or ;
or        = and  { "or"  and } ;
and       = cmp  { "and" cmp } ;
cmp       = add  { ("==" | "!=" | "<" | "<=" | ">" | ">=") add } ;
add       = mul  { ("+" | "-") mul } ;
mul       = unary { ("*" | "/" | "%") unary } ;
unary     = ( "-" | "!" | "not" ) unary | postfix ;
postfix   = primary { "[" expr "]" } ;
primary   = NUMBER | STRING | "true" | "false" | IDENT | IDENT "(" [ args ] ")"
          | "(" expr ")" | "[" [ args ] "]"
          | "measure" qarg
          | "sample" IDENT "(" [ args ] ")" [ "shots" add ] [ "on" IDENT ]
          | "expect" STRING "of" IDENT "(" [ args ] ")" [ "on" IDENT ]
          | "workload" "(" STRING { "," IDENT "=" expr } ")" ;
```

`/` rend un entier quand les deux opérandes sont entiers et que la division est exacte (`n / 2` peut dimensionner un registre), un flottant sinon.

## 4. Noyaux quantiques

- Portes : `h x y z s sdg t tdg sx` ; `rx ry rz p` (un angle) ; `cx cz swap` ; `cp crz` (un angle) ; `ccx`.
- `h q;` sans indice applique la porte à tout le registre.
- Les boucles `for` et les `if` sur des valeurs classiques sont évalués **à la compilation** : un noyau est spécialisé pour ses arguments au moment de l'appel.
- `let m = measure q[i];` produit un bit classique d'exécution. Il ne peut servir que de condition : `if m { x q[2]; }` (rétroaction, circuit dynamique).
- À la fin de `sample`, tous les qubits sont mesurés. Les chaînes de résultat placent le qubit `n-1` à gauche et le qubit 0 à droite (convention de Qiskit). Les chaînes de Pauli de `expect` suivent la même convention.
- Non pris en charge en v0 : appel d'un noyau depuis un autre, portes définies par l'utilisateur, portes contrôlées génériques, paramètres symboliques non liés.

## 5. Compilation

```
source ──lexer──▶ jetons ──parser──▶ AST ──spécialisation(args)──▶ SQIR ──optimiseur──▶ SQIR
                                                                        ├─▶ OpenQASM 3
                                                                        ├─▶ JSON
                                                                        └─▶ backend
```

**SQIR** : liste plate d'opérations `Op(nom, qubits, paramètres, bit_cible, conditions)`, sérialisable en JSON, accompagnée d'une estimation de ressources : qubits, nombre de portes, portes à deux qubits, profondeur, mesures intermédiaires, octets nécessaires au vecteur d'état (16 × 2ⁿ), caractère dynamique.

**Optimiseur** (jusqu'au point fixe) : annulation de paires inverses adjacentes (`h h`, `cx cx`, `s sdg`…), fusion de rotations de même axe, suppression des rotations nulles. Mesures, `reset` et opérations conditionnelles sont des barrières. Un test vérifie que le vecteur d'état est inchangé après optimisation.

**Partie classique** : `main` et les tâches sont exécutés par un interpréteur d'arbre. Seule la partie quantique est compilée vers une représentation intermédiaire. Une IR unifiée classique + quantique (cible : QIR/LLVM) est l'étape suivante.

## 6. Runtime et orchestrateur

| Construction | Décision |
|---|---|
| `sample k(...)` / `expect` sans `on` | Backend par défaut (`statevector`) si 16 × 2ⁿ octets tiennent dans la moitié de la RAM disponible ; sinon **erreur explicite** « non simulable ici » |
| `... on aer` / `on statevector` | Backend imposé |
| `... on qpu` | `BackendUnavailable` : aucun fournisseur configuré. Pas de repli silencieux sur un simulateur |
| `task ... on cpu` | Exécution locale |
| `task ... on worker` | Envoi au worker SWP/0 ; erreur s'il n'y en a pas |
| `task ... on any` | Worker si attaché et CPU local occupé à plus de 75 %, sinon local |
| `parallel { ... }` | Branches exécutées simultanément |

Chaque décision est ajoutée à `Runtime.trace` avec sa raison, sa durée et l'estimation de ressources.

## 7. Backends

| Nom | Nature | État |
|---|---|---|
| `statevector` | Simulateur exact NumPy intégré ; circuits dynamiques par énumération des branches de mesure | Opérationnel |
| `aer` | Qiskit Aer (C++) via conversion SQIR → `QuantumCircuit` | Opérationnel |
| `qasm3` | Export OpenQASM 3 (rechargé avec succès par l'importeur de Qiskit dans un test) | Opérationnel (export) |
| `qpu` | Matériel réel | **Non connecté** — refuse de s'exécuter |

## 8. Interopérabilité

| Cible | État |
|---|---|
| OpenQASM 3 | Export implémenté et vérifié |
| Qiskit | Conversion directe implémentée (backend Aer) |
| QIR | Non implémenté ; prévu comme IR unifiée |
| CUDA-Q | Non testé (pas de GPU Nvidia) ; atteignable via OpenQASM 3 → CUDA-Q d'après la littérature |
| Cirq, PennyLane, Q# | Non implémentés ; Cirq et PennyLane lisent l'OpenQASM (2 surtout), à vérifier |
| Fournisseurs (IBM, IonQ, Quantinuum, Braket) | Aucun ; demande un compte et un jeton |

## 9. Ce que SPATIAL Q ne prétend pas

- Il n'accélère rien par le quantique : tout ce qui a été exécuté est de la simulation classique, exponentielle en mémoire.
- Il ne rend pas un problème « quantique » : l'exemple `02_classical_distributed.sq` ne contient aucun qubit, et c'est voulu.
- Le simulateur intégré est plus lent qu'Aer au-delà de quelques qubits (voir `RESULTATS.md`).

## 10. Exemples fournis

| Fichier | Contenu |
|---|---|
| `examples/01_bell.sq` | Paire de Bell, échantillonnage et ⟨ZZ⟩ |
| `examples/02_classical_distributed.sq` | Deux moitiés d'un calcul en parallèle, aucun qubit |
| `examples/03_vqe_hybrid.sq` | Boucle variationnelle : descente de gradient classique + évaluations quantiques |
| `examples/04_teleport.sq` | Téléportation avec mesures intermédiaires et rétroaction |
| `examples/05_ghz_qft.sq` | Noyaux paramétrés ; QFT suivie de son inverse, annulée par l'optimiseur |

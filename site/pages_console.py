"""Docs pages for the console and its REST API. The headings repeat the console's own names (Overview, Apps, Jobs, Fleet,
API keys, Usage & billing, Settings, Admin) so that the docs and the product use one vocabulary."""
from scaffold import CFG, doc

IMG = lambda name, alt: f"@@IMG:{name}|{alt}@@"      # resolved in render(): the language prefix is only known then

SECTIONS = {
 "en": dict(
  title="Console and accounts", lead="Sign up, create apps linked to the infrastructure, get API keys, send jobs, watch usage, pay for what you use.",
  body='''<h2>The five steps</h2>
<ol><li><b>Create an account</b> (e-mail and password). A free monthly allowance is included.</li>
<li><b>Create an app</b> from the Overview. An app is a project: its own tenant id on the fleet, its own keys, usage and optional monthly budget.</li>
<li><b>Create an API key</b>: a <i>client</i> key sends work and reads results; a <i>node</i> key lets a machine join the fleet. The key is shown once.</li>
<li><b>Connect a machine</b>: <code>spatial agent --hub HUB --token-file node.tok</code>. It appears in Fleet within seconds.</li>
<li><b>Run a job</b> from Jobs (or <code>spatial fleet submit</code> with a client key). Usage is metered per finished task and billed monthly.</li></ol>
<p>The Overview shows these steps as a checklist and ticks them from what really exists on the hub.</p>
<h2>The console, page by page</h2>
<table><thead><tr><th>Page</th><th>What it is for</th></tr></thead><tbody>
<tr><td><b>Overview</b></td><td>The checklist, apps, active keys, nodes up, tasks and compute this month, estimated charge</td></tr>
<tr><td><b>Apps</b></td><td>One page per app with tabs: <i>Overview</i> (usage chart, recent tasks), <i>Keys</i>, <i>Connect</i> (CLI and Python snippets with your hub address), <i>Jobs</i>, <i>Settings</i> (name, budget, delete)</td></tr>
<tr><td><b>Jobs</b></td><td>Submit one of the hub's allow-listed workloads with its parameters, follow queued, running and finished jobs</td></tr>
<tr><td><b>Fleet</b></td><td>The machines that joined with your node keys (status, cores, CPU, RAM), queue counts, how to add a machine</td></tr>
<tr><td><b>API keys</b></td><td>Every hub credential of your apps; create, copy once, revoke</td></tr>
<tr><td><b>Usage &amp; billing</b></td><td>This month by app, free allowance, price per compute hour, invoices, payment</td></tr>
<tr><td><b>Settings</b></td><td><i>Profile</i>, <i>Security</i> (password, active sessions), <i>Account tokens</i> for the REST API, <i>Activity</i>, <i>Data</i> (export, delete account)</td></tr>
<tr><td><b>Admin</b></td><td>First account only: users, platform totals, hub status, configuration</td></tr></tbody></table>
''' + IMG("console-overview.png", "Console overview with the get-started checklist") + IMG("console-jobs.png", "Jobs page: submit a job and follow recent jobs") + IMG("console-fleet.png", "Fleet page: nodes that joined with node keys, queue counts, recent jobs") + '''
<h2>API keys and account tokens: two different things</h2>
<table><thead><tr><th></th><th>API key</th><th>Account token</th></tr></thead><tbody>
<tr><td>Used with</td><td>The <b>hub</b> (SWP/2): <code>spatial agent</code>, <code>spatial fleet</code>, any client</td><td>The <b>console REST API</b> (<a href="api.html">reference</a>): scripts that create apps, keys, read usage</td></tr>
<tr><td>Looks like</td><td><code>spc1.…~…</code> (a scoped hub credential named <code>app7:k3</code>)</td><td><code>spt_…</code></td></tr>
<tr><td>Scopes</td><td>client: <code>fleet:submit</code>, <code>fleet:read</code>. node: <code>fleet:report</code>, <code>fleet:work</code></td><td>read (GET only) or write</td></tr>
<tr><td>Shown</td><td>Once, at creation; only the last 4 characters are kept</td><td>Once; only a hash is kept</td></tr>
<tr><td>Revocation</td><td>At once, on the running hub (a revoked-names file it re-reads)</td><td>At once</td></tr></tbody></table>
<h2>How it is wired to the infrastructure</h2>
<table><thead><tr><th>In the console</th><th>On the hub</th></tr></thead><tbody>
<tr><td>An app</td><td>The tenant <code>app7</code>: fair share, queue and quotas apply to it</td></tr>
<tr><td>A key</td><td>A credential <code>app7:k3</code> signed with the hub's master key</td></tr>
<tr><td>A machine in Fleet</td><td>A node whose identity is its node key</td></tr>
<tr><td>A job</td><td>A task submitted with a short-lived client credential of the app</td></tr>
<tr><td>Usage</td><td>One line per finished task in the hub's usage file, read incrementally</td></tr></tbody></table>
<h2>Security</h2>
<ul><li>Passwords hashed with scrypt; the same message and the same work for unknown and known accounts; five wrong passwords lock the account for 15 minutes; sign-ups, logins and resets are rate-limited.</li>
<li>Session cookie <code>HttpOnly</code>, <code>SameSite=Strict</code> (<code>Secure</code> behind TLS), CSRF token and same-origin check on every change. Tokens are bearer credentials without cookies, so no CSRF; a token cannot create tokens, change the password or delete the account.</li>
<li>Reset links are single-use and expire in an hour and never reveal whether an address has an account; changing the password signs out every other session; you can list and end sessions.</li>
<li>One user cannot see or change another's app (same answer as for an app that does not exist). Strict content security policy: no inline script or style.</li>
<li>Binds to 127.0.0.1 unless you explicitly allow remote access: put TLS in front (the compose file uses Caddy).</li></ul>
<h2>Billing</h2>
<p>Price per compute hour and the monthly free allowance are configuration (<code>--pricing-file</code>); the defaults are an example price list. Invoices are created when a month with usage ends; tiny amounts are waived. Payment goes through Stripe Checkout when <code>STRIPE_SECRET_KEY</code> is set, and an invoice is marked paid only by Stripe's signed webhook. Without Stripe the console shows invoices and refuses to charge.</p>
<h2>Run and deploy</h2>
<p>Locally: <code>spatial platform serve</code> (see the panel). On a server: <code>docker compose --env-file deploy/.env up -d --build</code> starts the hub, the console and automatic HTTPS (<code>docs/DEPLOY.md</code>).</p>
<div class="callout warn"><b>Limits</b>One service process with SQLite. No teams or roles, no two-factor sign-in, no e-mail verification of new accounts, no taxes or PDF invoices. E-mails are sent only with SMTP configured, otherwise they stay in an outbox table. Tested end to end with a real hub and agents and in a driven browser session; payments only against a fake Stripe API, never with real money.</div>''',
  panels=[("Run it locally", '<span class="k">$ spatial token init --master-key-file hub.key\n$ spatial serve hub \\\n    --master-key-file hub.key \\\n    --usage-file usage.jsonl \\\n    --revoked-file revoked.txt\n$ spatial platform serve \\\n    --master-key-file hub.key \\\n    --hub 127.0.0.1:PORT \\\n    --usage-file usage.jsonl \\\n    --revoked-file revoked.txt</span>\n<span class="d">console on http://127.0.0.1:8090/</span>'),
          ("Production", '<span class="k">$ docker compose \\\n    --env-file deploy/.env \\\n    up -d --build</span>\n<span class="d">hub + console + HTTPS</span>')]),
 "fr": dict(
  title="Console et comptes", lead="Créer un compte, des apps liées à l'infrastructure, des clés d'API, envoyer des jobs, suivre l'usage, payer ce qu'on consomme.",
  body='''<h2>Les cinq étapes</h2>
<ol><li><b>Créer un compte</b> (e-mail et mot de passe). Une allocation gratuite mensuelle est incluse.</li>
<li><b>Créer une app</b> depuis la Vue d'ensemble (Overview). Une app est un projet : son propre identifiant de locataire sur la flotte, ses clés, son usage et un budget mensuel facultatif.</li>
<li><b>Créer une clé d'API</b> : une clé <i>client</i> envoie du travail et lit les résultats ; une clé <i>nœud</i> permet à une machine de rejoindre la flotte. La clé n'est affichée qu'une fois.</li>
<li><b>Connecter une machine</b> : <code>spatial agent --hub HUB --token-file node.tok</code>. Elle apparaît dans Fleet en quelques secondes.</li>
<li><b>Lancer un job</b> depuis Jobs (ou <code>spatial fleet submit</code> avec une clé client). L'usage est mesuré par tâche terminée et facturé chaque mois.</li></ol>
<p>L'Overview affiche ces étapes comme une liste de contrôle et les coche d'après ce qui existe réellement sur le hub.</p>
<h2>La console, page par page</h2>
<table><thead><tr><th>Page</th><th>À quoi elle sert</th></tr></thead><tbody>
<tr><td><b>Overview</b></td><td>La liste de contrôle, apps, clés actives, nœuds en ligne, tâches et calcul du mois, charge estimée</td></tr>
<tr><td><b>Apps</b></td><td>Une page par app avec onglets : <i>Overview</i> (graphique d'usage, tâches récentes), <i>Keys</i>, <i>Connect</i> (extraits CLI et Python avec l'adresse de votre hub), <i>Jobs</i>, <i>Settings</i> (nom, budget, suppression)</td></tr>
<tr><td><b>Jobs</b></td><td>Soumettre une des charges autorisées du hub avec ses paramètres, suivre les jobs en file, en cours et terminés</td></tr>
<tr><td><b>Fleet</b></td><td>Les machines qui ont rejoint avec vos clés nœud (état, cœurs, CPU, RAM), compteurs de la file, comment ajouter une machine</td></tr>
<tr><td><b>API keys</b></td><td>Tous les identifiants de hub de vos apps ; créer, copier une fois, révoquer</td></tr>
<tr><td><b>Usage &amp; billing</b></td><td>Le mois par app, allocation gratuite, prix par heure de calcul, factures, paiement</td></tr>
<tr><td><b>Settings</b></td><td><i>Profile</i>, <i>Security</i> (mot de passe, sessions actives), <i>Account tokens</i> pour l'API REST, <i>Activity</i>, <i>Data</i> (export, suppression du compte)</td></tr>
<tr><td><b>Admin</b></td><td>Premier compte seulement : utilisateurs, totaux de la plateforme, état du hub, configuration</td></tr></tbody></table>
''' + IMG("console-overview.png", "Vue d'ensemble de la console avec la liste de démarrage") + IMG("console-jobs.png", "Page Jobs : soumettre un job et suivre les jobs récents") + IMG("console-fleet.png", "Page Fleet : nœuds ayant rejoint avec des clés nœud, compteurs de la file, jobs récents") + '''
<h2>Clés d'API et jetons de compte : deux choses différentes</h2>
<table><thead><tr><th></th><th>Clé d'API</th><th>Jeton de compte</th></tr></thead><tbody>
<tr><td>Sert avec</td><td>Le <b>hub</b> (SWP/2) : <code>spatial agent</code>, <code>spatial fleet</code>, tout client</td><td>L'<b>API REST de la console</b> (<a href="api.html">référence</a>) : scripts qui créent apps et clés, lisent l'usage</td></tr>
<tr><td>Ressemble à</td><td><code>spc1.…~…</code> (un identifiant de hub à portée limitée nommé <code>app7:k3</code>)</td><td><code>spt_…</code></td></tr>
<tr><td>Portées</td><td>client : <code>fleet:submit</code>, <code>fleet:read</code>. nœud : <code>fleet:report</code>, <code>fleet:work</code></td><td>read (GET seulement) ou write</td></tr>
<tr><td>Affichage</td><td>Une fois, à la création ; seuls les 4 derniers caractères sont gardés</td><td>Une fois ; seul un hachage est gardé</td></tr>
<tr><td>Révocation</td><td>Immédiate, sur le hub en marche (fichier de noms révoqués relu)</td><td>Immédiate</td></tr></tbody></table>
<h2>Comment c'est relié à l'infrastructure</h2>
<table><thead><tr><th>Dans la console</th><th>Sur le hub</th></tr></thead><tbody>
<tr><td>Une app</td><td>Le locataire <code>app7</code> : équité, file et quotas s'appliquent à lui</td></tr>
<tr><td>Une clé</td><td>Un identifiant <code>app7:k3</code> signé avec la clé maîtresse du hub</td></tr>
<tr><td>Une machine dans Fleet</td><td>Un nœud dont l'identité est sa clé nœud</td></tr>
<tr><td>Un job</td><td>Une tâche soumise avec un identifiant client de courte durée de l'app</td></tr>
<tr><td>L'usage</td><td>Une ligne par tâche terminée dans le fichier d'usage du hub, lu au fil de l'eau</td></tr></tbody></table>
<h2>Sécurité</h2>
<ul><li>Mots de passe hachés avec scrypt ; même message et même travail pour un compte inconnu ou connu ; cinq mots de passe faux verrouillent le compte 15 minutes ; inscriptions, connexions et réinitialisations sont limitées en fréquence.</li>
<li>Cookie de session <code>HttpOnly</code>, <code>SameSite=Strict</code> (<code>Secure</code> derrière TLS), jeton CSRF et contrôle de même origine à chaque changement. Les jetons sont des identifiants porteurs sans cookie, donc sans CSRF ; un jeton ne peut ni créer de jeton, ni changer le mot de passe, ni supprimer le compte.</li>
<li>Les liens de réinitialisation sont à usage unique, expirent en une heure et ne révèlent jamais si une adresse a un compte ; changer le mot de passe déconnecte toutes les autres sessions ; vous pouvez lister et fermer vos sessions.</li>
<li>Un utilisateur ne peut ni voir ni modifier l'app d'un autre (même réponse que pour une app inexistante). Politique de sécurité de contenu stricte : ni script ni style en ligne.</li>
<li>Écoute sur 127.0.0.1 sauf autorisation explicite : mettez TLS devant (le fichier compose utilise Caddy).</li></ul>
<h2>Facturation</h2>
<p>Le prix par heure de calcul et l'allocation gratuite mensuelle sont de la configuration (<code>--pricing-file</code>) ; les valeurs par défaut sont une grille d'exemple. Les factures sont créées à la fin d'un mois avec usage ; les petits montants sont annulés. Le paiement passe par Stripe Checkout quand <code>STRIPE_SECRET_KEY</code> est défini, et une facture n'est marquée payée que par le webhook signé de Stripe. Sans Stripe, la console affiche les factures et refuse de débiter.</p>
<h2>Lancer et déployer</h2>
<p>En local : <code>spatial platform serve</code> (voir le panneau). Sur un serveur : <code>docker compose --env-file deploy/.env up -d --build</code> démarre le hub, la console et HTTPS automatique (<code>docs/DEPLOY.md</code>).</p>
<div class="callout warn"><b>Limites</b>Un seul processus avec SQLite. Pas d'équipes ni de rôles, pas de double authentification, pas de vérification de l'e-mail à l'inscription, ni taxes ni factures PDF. Les e-mails ne partent qu'avec SMTP configuré, sinon ils restent dans une table. Testé de bout en bout avec un vrai hub et de vrais agents et dans une session de navigateur pilotée ; paiements seulement contre une fausse API Stripe, jamais avec de l'argent réel.</div>''',
  panels=[("Lancer en local", '<span class="k">$ spatial token init --master-key-file hub.key\n$ spatial serve hub \\\n    --master-key-file hub.key \\\n    --usage-file usage.jsonl \\\n    --revoked-file revoked.txt\n$ spatial platform serve \\\n    --master-key-file hub.key \\\n    --hub 127.0.0.1:PORT \\\n    --usage-file usage.jsonl \\\n    --revoked-file revoked.txt</span>\n<span class="d">console sur http://127.0.0.1:8090/</span>'),
          ("Production", '<span class="k">$ docker compose \\\n    --env-file deploy/.env \\\n    up -d --build</span>\n<span class="d">hub + console + HTTPS</span>')]),
}

API_EN = '''<p>The console's REST API is what the console itself uses. Base URL: your console (for example <code>http://127.0.0.1:8090</code>). Bodies and answers are JSON. Errors: <code>{"error": "message"}</code> with the HTTP status (400 bad input, 401 not signed in, 402 budget reached, 403 refused, 404 not found or not yours, 409 conflict, 429 too many attempts).</p>
<h2>Authentication</h2>
<ul><li><b>Browser session</b>: <code>POST /api/login</code> sets an <code>HttpOnly</code> cookie; send the <code>csrf</code> value it returns in an <code>X-CSRF-Token</code> header on every POST, PATCH and DELETE.</li>
<li><b>Account token</b> (scripts): create one in Settings, then <code>Authorization: Bearer spt_…</code>. No cookie, no CSRF. A <i>read</i> token may only GET. Tokens cannot create tokens, change the password, delete the account or list sessions.</li></ul>
<pre><code>curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8090/api/apps
curl -X POST -H "Authorization: Bearer $WRITE_TOKEN" -H "Content-Type: application/json" \\
     -d '{"name":"batch"}' http://127.0.0.1:8090/api/apps</code></pre>
<h2>Endpoints</h2>
<table><thead><tr><th>Method and path</th><th>What it does</th></tr></thead><tbody>
<tr><td><code>POST /api/signup</code> · <code>/api/login</code> · <code>/api/logout</code></td><td>Create an account and sign in; sign in; sign out</td></tr>
<tr><td><code>POST /api/password/reset-request</code> · <code>/api/password/reset</code> · <code>/api/password/change</code></td><td>Reset by e-mailed link (always answers the same); change (signs out other sessions)</td></tr>
<tr><td><code>GET /api/me</code> · <code>PATCH /api/me</code> · <code>DELETE /api/me</code> · <code>GET /api/export</code></td><td>Profile; rename; delete the account (password required, no open invoice); export your data</td></tr>
<tr><td><code>GET /api/overview</code></td><td>Checklist, counts, estimated charge</td></tr>
<tr><td><code>GET</code> · <code>POST /api/apps</code>; <code>GET</code> · <code>PATCH</code> · <code>DELETE /api/apps/{id}</code></td><td>List, create (<code>name</code>, <code>description</code>, <code>budget_usd</code>), read, update, delete (revokes its keys)</td></tr>
<tr><td><code>POST /api/apps/{id}/keys</code> · <code>DELETE /api/apps/{id}/keys/{kid}</code></td><td>Create a hub key (<code>name</code>, <code>kind</code>: client or node, <code>ttl_days</code>; the token is in the answer, once); revoke</td></tr>
<tr><td><code>GET /api/apps/{id}/usage?days=30</code></td><td>Tasks and compute seconds per day, recent tasks</td></tr>
<tr><td><code>GET /api/workloads</code></td><td>Workloads you may submit, with parameter names and defaults</td></tr>
<tr><td><code>POST /api/apps/{id}/jobs</code> · <code>GET /api/apps/{id}/jobs/{task}</code></td><td>Submit (<code>workload</code>, <code>params</code>) and read a job's state and result</td></tr>
<tr><td><code>POST /api/apps/{id}/test-job</code></td><td>Run a small job and wait for it</td></tr>
<tr><td><code>GET /api/fleet</code></td><td>Your nodes, queue counts and recent jobs, read from the hub</td></tr>
<tr><td><code>GET /api/billing</code> · <code>POST /api/billing/pay</code></td><td>Estimate, price list, invoices; start a Stripe Checkout for an open invoice</td></tr>
<tr><td><code>GET</code> · <code>POST /api/tokens</code>; <code>DELETE /api/tokens/{id}</code></td><td>Account tokens (browser session only for create and revoke)</td></tr>
<tr><td><code>GET /api/sessions</code> · <code>DELETE /api/sessions/{id}</code> · <code>GET /api/activity</code></td><td>Active sessions, sign one out; security activity</td></tr>
<tr><td><code>GET /api/admin/overview</code> · <code>/api/admin/users</code></td><td>First account only</td></tr>
<tr><td><code>POST /api/billing/webhook</code></td><td>Stripe's signed webhook (no session; the signature is the authentication)</td></tr>
<tr><td><code>GET /api/health</code></td><td><code>{"ok": true}</code></td></tr></tbody></table>
<h2>Example: from nothing to a result</h2>
<pre><code># with a write token
APP=$(curl -s -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d '{"name":"demo"}' $BASE/api/apps | jq .app.id)
curl -s -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d '{"name":"n","kind":"node"}' $BASE/api/apps/$APP/keys | jq -r .key.token &gt; node.tok
spatial agent --hub HUB:7700 --token-file node.tok &amp;
curl -s -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" \\
     -d '{"workload":"montecarlo_pi","params":{"samples":1000000}}' $BASE/api/apps/$APP/jobs</code></pre>
<div class="callout warn"><b>Limits</b>No pagination and no webhooks to you (usage is polled), no per-token rate limit, one unversioned API surface that may change. Tested through HTTP in <code>tests/test_platform.py</code>.</div>'''
API_FR = '''<p>L'API REST de la console est celle que la console utilise elle-même. URL de base : votre console (par exemple <code>http://127.0.0.1:8090</code>). Corps et réponses en JSON. Erreurs : <code>{"error": "message"}</code> avec le statut HTTP (400 entrée invalide, 401 non connecté, 402 budget atteint, 403 refusé, 404 introuvable ou pas à vous, 409 conflit, 429 trop de tentatives).</p>
<h2>Authentification</h2>
<ul><li><b>Session de navigateur</b> : <code>POST /api/login</code> pose un cookie <code>HttpOnly</code> ; envoyez la valeur <code>csrf</code> renvoyée dans un en-tête <code>X-CSRF-Token</code> sur chaque POST, PATCH et DELETE.</li>
<li><b>Jeton de compte</b> (scripts) : créez-en un dans Settings, puis <code>Authorization: Bearer spt_…</code>. Pas de cookie, pas de CSRF. Un jeton <i>read</i> ne peut que faire des GET. Les jetons ne peuvent ni créer de jeton, ni changer le mot de passe, ni supprimer le compte, ni lister les sessions.</li></ul>
<pre><code>curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8090/api/apps
curl -X POST -H "Authorization: Bearer $WRITE_TOKEN" -H "Content-Type: application/json" \\
     -d '{"name":"batch"}' http://127.0.0.1:8090/api/apps</code></pre>
<h2>Points d'entrée</h2>
<table><thead><tr><th>Méthode et chemin</th><th>Ce que ça fait</th></tr></thead><tbody>
<tr><td><code>POST /api/signup</code> · <code>/api/login</code> · <code>/api/logout</code></td><td>Créer un compte et se connecter ; se connecter ; se déconnecter</td></tr>
<tr><td><code>POST /api/password/reset-request</code> · <code>/api/password/reset</code> · <code>/api/password/change</code></td><td>Réinitialiser par lien envoyé (répond toujours pareil) ; changer (déconnecte les autres sessions)</td></tr>
<tr><td><code>GET /api/me</code> · <code>PATCH /api/me</code> · <code>DELETE /api/me</code> · <code>GET /api/export</code></td><td>Profil ; renommer ; supprimer le compte (mot de passe requis, aucune facture ouverte) ; exporter vos données</td></tr>
<tr><td><code>GET /api/overview</code></td><td>Liste de contrôle, compteurs, charge estimée</td></tr>
<tr><td><code>GET</code> · <code>POST /api/apps</code> ; <code>GET</code> · <code>PATCH</code> · <code>DELETE /api/apps/{id}</code></td><td>Lister, créer (<code>name</code>, <code>description</code>, <code>budget_usd</code>), lire, modifier, supprimer (révoque ses clés)</td></tr>
<tr><td><code>POST /api/apps/{id}/keys</code> · <code>DELETE /api/apps/{id}/keys/{kid}</code></td><td>Créer une clé de hub (<code>name</code>, <code>kind</code> : client ou node, <code>ttl_days</code> ; le jeton est dans la réponse, une fois) ; révoquer</td></tr>
<tr><td><code>GET /api/apps/{id}/usage?days=30</code></td><td>Tâches et secondes de calcul par jour, tâches récentes</td></tr>
<tr><td><code>GET /api/workloads</code></td><td>Charges que vous pouvez soumettre, avec noms de paramètres et valeurs par défaut</td></tr>
<tr><td><code>POST /api/apps/{id}/jobs</code> · <code>GET /api/apps/{id}/jobs/{task}</code></td><td>Soumettre (<code>workload</code>, <code>params</code>) et lire l'état et le résultat d'un job</td></tr>
<tr><td><code>POST /api/apps/{id}/test-job</code></td><td>Lancer un petit job et l'attendre</td></tr>
<tr><td><code>GET /api/fleet</code></td><td>Vos nœuds, compteurs de la file et jobs récents, lus sur le hub</td></tr>
<tr><td><code>GET /api/billing</code> · <code>POST /api/billing/pay</code></td><td>Estimation, grille de prix, factures ; démarrer un Stripe Checkout pour une facture ouverte</td></tr>
<tr><td><code>GET</code> · <code>POST /api/tokens</code> ; <code>DELETE /api/tokens/{id}</code></td><td>Jetons de compte (session de navigateur seulement pour créer et révoquer)</td></tr>
<tr><td><code>GET /api/sessions</code> · <code>DELETE /api/sessions/{id}</code> · <code>GET /api/activity</code></td><td>Sessions actives, en fermer une ; activité de sécurité</td></tr>
<tr><td><code>GET /api/admin/overview</code> · <code>/api/admin/users</code></td><td>Premier compte seulement</td></tr>
<tr><td><code>POST /api/billing/webhook</code></td><td>Webhook signé de Stripe (pas de session ; la signature authentifie)</td></tr>
<tr><td><code>GET /api/health</code></td><td><code>{"ok": true}</code></td></tr></tbody></table>
<h2>Exemple : de rien à un résultat</h2>
<pre><code># avec un jeton write
APP=$(curl -s -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d '{"name":"demo"}' $BASE/api/apps | jq .app.id)
curl -s -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d '{"name":"n","kind":"node"}' $BASE/api/apps/$APP/keys | jq -r .key.token &gt; node.tok
spatial agent --hub HUB:7700 --token-file node.tok &amp;
curl -s -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" \\
     -d '{"workload":"montecarlo_pi","params":{"samples":1000000}}' $BASE/api/apps/$APP/jobs</code></pre>
<div class="callout warn"><b>Limites</b>Pas de pagination ni de webhooks vers vous (l'usage s'interroge), pas de limite de débit par jeton, une surface d'API non versionnée susceptible de changer. Testée via HTTP dans <code>tests/test_platform.py</code>.</div>'''

def _imgs(html):
    import re
    return re.sub(r"@@IMG:([^|]+)\|([^@]+)@@", lambda m: f'<p><img src="{CFG["prefix"]}../assets/{m.group(1)}" alt="{m.group(2)}" style="max-width:100%;border:1px solid var(--line)"></p>', html)


def render(lang):
    t = SECTIONS[lang]
    doc("console", t["title"], t["lead"], _imgs(t["body"]), t["panels"])
    api = API_EN if lang == "en" else API_FR
    panels = [("Authenticate", '<span class="k">$ curl -H "Authorization: \\\n    Bearer spt_…" \\\n    $BASE/api/apps</span>'), ("Create a token", '<span class="d">Console → Settings → Account tokens</span>')] if lang == "en" else \
             [("S'authentifier", '<span class="k">$ curl -H "Authorization: \\\n    Bearer spt_…" \\\n    $BASE/api/apps</span>'), ("Créer un jeton", '<span class="d">Console → Settings → Account tokens</span>')]
    doc("api", "REST API" if lang == "en" else "API REST", "Everything the console does, for scripts." if lang == "en" else "Tout ce que fait la console, pour les scripts.", api, panels)

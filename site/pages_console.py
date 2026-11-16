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
<tr><td><b>Team</b></td><td>Members, roles, invitations and the organization's name; the switcher at the top of the sidebar changes organization</td></tr>
<tr><td><b>Usage &amp; billing</b></td><td>This month by app, free allowance, price per compute hour, tax, numbered invoices with PDF, payment, billing details (admins and owners)</td></tr>
<tr><td><b>Settings</b></td><td><i>Profile</i>, <i>Security</i> (two-factor sign-in, password, active sessions), <i>Account tokens</i> for the REST API, <i>Activity</i>, <i>Data</i> (export, delete account)</td></tr>
<tr><td><b>Admin</b></td><td>First account only: users, platform totals, hub status, <b>prices and tax</b>, company details for invoices, e-mail status and test, mail queue</td></tr></tbody></table>
<h2>Teams and roles</h2>
<p>Everything (apps, keys, jobs, usage, invoices) belongs to an <b>organization</b>. Every account has a personal workspace with one member; create an organization to work with others and invite them by e-mail (the invitation is for one address, single use, valid seven days).</p>
<table><thead><tr><th>Role</th><th>Can</th></tr></thead><tbody>
<tr><td><b>viewer</b></td><td>See apps, usage, fleet and jobs</td></tr>
<tr><td><b>member</b></td><td>+ create apps, API keys and jobs; rename apps</td></tr>
<tr><td><b>admin</b></td><td>+ invite and remove members, set budgets, delete apps, see billing, pay, edit billing details</td></tr>
<tr><td><b>owner</b></td><td>+ appoint owners, delete the organization. At least one owner always remains</td></tr></tbody></table>
<p>Behind the four built-in roles there are <b>permissions</b> (<code>apps.write</code>, <code>apps.delete</code>, <code>apps.budget</code>, <code>keys.write</code>, <code>jobs.submit</code>, <code>billing.read</code>, <code>billing.pay</code>, <code>org.manage</code>, <code>members.manage</code>; <code>org.delete</code> and <code>members.owner</code> stay with owners). On the Team page you can define up to ten <b>custom roles</b> (for example a <i>billing-clerk</i> who sees invoices and pays them but cannot touch apps). One rule closes the escalation hole: nobody can create or hand out a role containing a permission they do not hold themselves.</p>
''' + IMG("console-overview.png", "Console overview with the get-started checklist") + IMG("console-jobs.png", "Jobs page: submit a job and follow recent jobs") + IMG("console-fleet.png", "Fleet page: nodes that joined with node keys, queue counts, recent jobs") + IMG("console-team.png", "Team page: members, roles, invitations") + IMG("console-admin.png", "Admin page: prices and tax, company details, e-mail") + IMG("console-roles.png", "Team page: built-in and custom roles with their permissions") + '''
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
<h2>Account security</h2>
<ul><li><b>Passwords</b> hashed with scrypt; same message and same work for unknown and known accounts; five wrong passwords lock the account for 15 minutes; sign-ups, logins, resets and API calls are rate-limited (600 requests a minute per user, 120 per token).</li>
<li><b>Two-factor sign-in</b> (Settings, Security): a code from any authenticator app (TOTP, RFC 6238) after the password; eight single-use recovery codes shown once; a code works once; five tries per sign-in attempt; turning it off needs the password and a code and ends every session.</li>
<li><b>E-mail verification</b>: new accounts get a link; when the server can send e-mail, API keys, jobs and organizations need a verified address (the operator account is exempt). Without SMTP it is not enforced, because nobody could verify.</li>
<li><b>Sessions</b>: HttpOnly, SameSite=Strict (Secure behind TLS) cookie, CSRF token and same-origin check on every change; list and end sessions; changing the password ends the others. Tokens are bearer credentials without cookies, so no CSRF; a token cannot create tokens, change the password or delete the account.</li>
<li><b>Isolation</b>: a user sees only organizations they belong to; asking for another organization's data gives the same answer as for something that does not exist. Strict content security policy: no inline script or style.</li>
<li>Binds to 127.0.0.1 unless you explicitly allow remote access: put TLS in front (the compose file uses Caddy).</li></ul>
<h2>Single sign-on</h2>
<p>If the operator configures an OpenID Connect provider (Google, Microsoft Entra, Okta, Keycloak…; <code>--oidc-issuer</code>, <code>--oidc-client-id</code>, <code>OIDC_CLIENT_SECRET</code>), the sign-in page shows <i>Sign in with …</i>. The flow is the authorization code with PKCE; the ID token is verified here (RS256 signature against the provider's keys, issuer, audience, expiry, nonce, confirmed e-mail), the state is single use and expires in ten minutes, and the operator can limit it to some e-mail domains or to existing accounts. A user who turned on two-factor sign-in still has to give the code. SAML is deliberately not built in: put an OpenID Connect broker (Dex, Keycloak) in front of your SAML provider. This flow is tested against a real provider (Dex).</p>
<h2>Billing, tax and invoices</h2>
<p>The operator sets prices in Admin (price per compute hour, free monthly allowance, minimum invoice, currency) and tax (a default rate, rates by customer country, optional simplified reverse charge for a customer with a VAT id abroad). Prices apply from then on; <b>invoices already issued keep the prices they were issued with</b>. Organizations enter their billing details (name, address, country, VAT id): a VAT id is checked for format for the EU, UK, Switzerland and Norway and for the <b>check digit</b> where the algorithm is public (AT, BE, DE, DK, FR, IT, PL, PT), and optionally against the European Commission's VIES service; the console says which check passed. The operator can issue <b>credit notes</b> (numbered <code>CN-2026-00001</code>, with PDF, tax credited at the invoice's rate): an unpaid invoice shrinks; for a paid one the refund goes through Stripe when the payment is known, otherwise the note is marked <i>refund due</i>. Admin warns about what is missing before you invoice (company name, address, VAT id, country). At the end of a month with usage an invoice is created with a <b>gap-free number</b> (<code>INV-2026-00001</code>), subtotal, tax and total, and can be downloaded as <b>PDF</b>; amounts under the minimum are waived and get no number. Payment goes through Stripe Checkout when <code>STRIPE_SECRET_KEY</code> is set, and an invoice is marked paid only by Stripe's signed webhook; without Stripe the console shows invoices and refuses to charge.</p>
<p>Until the operator saves real prices, the console says plainly that it is using example prices.</p>
<h2>E-mail</h2>
<p>Messages (verification, invitations, password reset) go through a queue: delivered over SMTP (<code>--smtp-host</code>, STARTTLS or implicit TLS) and retried with growing delays when the server is down; without SMTP they stay visible in Admin. Admin has a test-message button.</p>
<h2>Run and deploy</h2>
<p>Locally: <code>spatial platform serve</code> (see the panel). On a server: <code>docker compose --env-file deploy/.env up -d --build</code> starts the hub, the console and automatic HTTPS (<code>docs/DEPLOY.md</code>).</p>
<div class="callout warn"><b>Limits</b>One service process with SQLite. The tax handling is a rate table, a simplified reverse-charge switch, VAT-number checks, credit notes, a required-fields checklist for FR, DE, ES, IT, NL, BE and GB, and UBL 2.1 XML export (valid against the official schemas, not checked against the Peppol business rules, not sent through any network): it is not a tax-compliance engine, have an accountant check it before you invoice. No SAML (use an OpenID Connect broker). Two-factor setup draws a QR code with a small encoder checked module for module against an independent library; scan it or type the key. Custom roles combine a fixed list of permissions; a member or invitation can be limited to some apps. Credit notes cover partial or full amounts, not other corrections. E-mail is tested against Mailpit (STARTTLS and login), payments against stripe-mock, sign-in against Dex: real servers, but never a live provider or real money.</div>''',
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
<tr><td><b>Team</b></td><td>Membres, rôles, invitations et nom de l'organisation ; le sélecteur en haut de la barre latérale change d'organisation</td></tr>
<tr><td><b>Usage &amp; billing</b></td><td>Le mois par app, allocation gratuite, prix par heure de calcul, taxe, factures numérotées avec PDF, paiement, coordonnées de facturation (admins et propriétaires)</td></tr>
<tr><td><b>Settings</b></td><td><i>Profile</i>, <i>Security</i> (double authentification, mot de passe, sessions actives), <i>Account tokens</i> pour l'API REST, <i>Activity</i>, <i>Data</i> (export, suppression du compte)</td></tr>
<tr><td><b>Admin</b></td><td>Premier compte seulement : utilisateurs, totaux de la plateforme, état du hub, <b>prix et taxe</b>, coordonnées de la société pour les factures, état et test de l'e-mail, file des messages</td></tr></tbody></table>
<h2>Équipes et rôles</h2>
<p>Tout (apps, clés, jobs, usage, factures) appartient à une <b>organisation</b>. Chaque compte a un espace personnel à un seul membre ; créez une organisation pour travailler à plusieurs et invitez par e-mail (l'invitation vaut pour une adresse, à usage unique, valable sept jours).</p>
<table><thead><tr><th>Rôle</th><th>Peut</th></tr></thead><tbody>
<tr><td><b>viewer</b></td><td>Voir apps, usage, flotte et jobs</td></tr>
<tr><td><b>member</b></td><td>+ créer apps, clés d'API et jobs ; renommer les apps</td></tr>
<tr><td><b>admin</b></td><td>+ inviter et retirer des membres, fixer les budgets, supprimer des apps, voir la facturation, payer, modifier les coordonnées</td></tr>
<tr><td><b>owner</b></td><td>+ nommer des propriétaires, supprimer l'organisation. Il reste toujours au moins un propriétaire</td></tr></tbody></table>
<p>Derrière les quatre rôles intégrés il y a des <b>permissions</b> (<code>apps.write</code>, <code>apps.delete</code>, <code>apps.budget</code>, <code>keys.write</code>, <code>jobs.submit</code>, <code>billing.read</code>, <code>billing.pay</code>, <code>org.manage</code>, <code>members.manage</code> ; <code>org.delete</code> et <code>members.owner</code> restent aux propriétaires). Sur la page Team, vous pouvez définir jusqu'à dix <b>rôles personnalisés</b> (par exemple un <i>billing-clerk</i> qui voit les factures et les paie mais ne touche pas aux apps). Une règle ferme la faille d'escalade : personne ne peut créer ni attribuer un rôle contenant une permission qu'il ne détient pas lui-même.</p>
''' + IMG("console-overview.png", "Vue d'ensemble de la console avec la liste de démarrage") + IMG("console-jobs.png", "Page Jobs : soumettre un job et suivre les jobs récents") + IMG("console-fleet.png", "Page Fleet : nœuds ayant rejoint avec des clés nœud, compteurs de la file, jobs récents") + IMG("console-team.png", "Page Team : membres, rôles, invitations") + IMG("console-admin.png", "Page Admin : prix et taxe, coordonnées de la société, e-mail") + IMG("console-roles.png", "Page Team : rôles intégrés et personnalisés avec leurs permissions") + '''
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
<h2>Sécurité du compte</h2>
<ul><li><b>Mots de passe</b> hachés avec scrypt ; même message et même travail pour un compte inconnu ou connu ; cinq mots de passe faux verrouillent le compte 15 minutes ; inscriptions, connexions, réinitialisations et appels d'API sont limités en fréquence (600 requêtes par minute et par utilisateur, 120 par jeton).</li>
<li><b>Double authentification</b> (Settings, Security) : un code d'une application d'authentification (TOTP, RFC 6238) après le mot de passe ; huit codes de secours à usage unique affichés une fois ; un code ne sert qu'une fois ; cinq essais par tentative de connexion ; la désactiver exige le mot de passe et un code et ferme toutes les sessions.</li>
<li><b>Vérification de l'e-mail</b> : les nouveaux comptes reçoivent un lien ; quand le serveur peut envoyer des e-mails, clés d'API, jobs et organisations exigent une adresse vérifiée (le compte opérateur est exempté). Sans SMTP, ce n'est pas imposé, car personne ne pourrait vérifier.</li>
<li><b>Sessions</b> : cookie HttpOnly, SameSite=Strict (Secure derrière TLS), jeton CSRF et contrôle de même origine à chaque changement ; lister et fermer des sessions ; changer le mot de passe ferme les autres. Les jetons sont des identifiants porteurs sans cookie, donc sans CSRF ; un jeton ne peut ni créer de jeton, ni changer le mot de passe, ni supprimer le compte.</li>
<li><b>Isolation</b> : un utilisateur ne voit que les organisations dont il est membre ; demander les données d'une autre donne la même réponse que pour quelque chose d'inexistant. Politique de sécurité de contenu stricte : ni script ni style en ligne.</li>
<li>Écoute sur 127.0.0.1 sauf autorisation explicite : mettez TLS devant (le fichier compose utilise Caddy).</li></ul>
<h2>Connexion unique (SSO)</h2>
<p>Si l'opérateur configure un fournisseur OpenID Connect (Google, Microsoft Entra, Okta, Keycloak… ; <code>--oidc-issuer</code>, <code>--oidc-client-id</code>, <code>OIDC_CLIENT_SECRET</code>), la page de connexion affiche <i>Sign in with …</i>. Le flux est le code d'autorisation avec PKCE ; le jeton d'identité est vérifié ici (signature RS256 contre les clés du fournisseur, émetteur, audience, expiration, nonce, e-mail confirmé), l'état est à usage unique et expire en dix minutes, et l'opérateur peut limiter à certains domaines d'e-mail ou aux comptes existants. Un utilisateur qui a activé la double authentification doit toujours donner le code. SAML n'est volontairement pas intégré : placez un courtier OpenID Connect (Dex, Keycloak) devant votre fournisseur SAML. Ce flux est testé contre un vrai fournisseur (Dex).</p>
<h2>Facturation, taxe et factures</h2>
<p>L'opérateur fixe les prix dans Admin (prix par heure de calcul, allocation gratuite mensuelle, facture minimale, devise) et la taxe (un taux par défaut, des taux par pays du client, une autoliquidation simplifiée facultative pour un client avec un numéro de TVA à l'étranger). Les prix s'appliquent à partir de là ; <b>les factures déjà émises gardent les prix avec lesquels elles ont été émises</b>. Les organisations saisissent leurs coordonnées de facturation (nom, adresse, pays, numéro de TVA) : un numéro de TVA est vérifié pour le format (UE, Royaume-Uni, Suisse, Norvège) et pour la <b>clé de contrôle</b> là où l'algorithme est public (AT, BE, DE, DK, FR, IT, PL, PT), et facultativement auprès du service VIES de la Commission européenne ; la console indique quelle vérification a réussi. L'opérateur peut émettre des <b>avoirs</b> (numérotés <code>CN-2026-00001</code>, avec PDF, taxe créditée au taux de la facture) : une facture impayée diminue ; pour une facture payée, le remboursement passe par Stripe quand le paiement est connu, sinon l'avoir est marqué <i>remboursement dû</i>. Admin signale ce qui manque avant de facturer (nom de société, adresse, numéro de TVA, pays). À la fin d'un mois avec usage, une facture est créée avec un <b>numéro sans trou</b> (<code>INV-2026-00001</code>), sous-total, taxe et total, téléchargeable en <b>PDF</b> ; les montants sous le minimum sont annulés et n'ont pas de numéro. Le paiement passe par Stripe Checkout quand <code>STRIPE_SECRET_KEY</code> est défini, et une facture n'est marquée payée que par le webhook signé de Stripe ; sans Stripe, la console affiche les factures et refuse de débiter.</p>
<p>Tant que l'opérateur n'a pas enregistré de vrais prix, la console dit clairement qu'elle utilise des prix d'exemple.</p>
<h2>E-mail</h2>
<p>Les messages (vérification, invitations, réinitialisation) passent par une file : remis par SMTP (<code>--smtp-host</code>, STARTTLS ou TLS implicite) et réessayés avec des délais croissants quand le serveur est en panne ; sans SMTP ils restent visibles dans Admin. Admin a un bouton de message de test.</p>
<h2>Lancer et déployer</h2>
<p>En local : <code>spatial platform serve</code> (voir le panneau). Sur un serveur : <code>docker compose --env-file deploy/.env up -d --build</code> démarre le hub, la console et HTTPS automatique (<code>docs/DEPLOY.md</code>).</p>
<div class="callout warn"><b>Limites</b>Un seul processus avec SQLite. La taxe est une table de taux, un interrupteur d'autoliquidation simplifiée, des vérifications de numéro de TVA, des avoirs, une liste de champs obligatoires pour FR, DE, ES, IT, NL, BE et GB, et un export XML UBL 2.1 (valide contre les schémas officiels, non vérifié contre les règles métier Peppol, envoyé nulle part) : ce n'est pas un moteur de conformité fiscale, faites relire par un comptable avant de facturer. Pas de SAML (utilisez un courtier OpenID Connect). La double authentification dessine un QR code avec un petit encodeur vérifié module par module contre une bibliothèque indépendante ; scannez-le ou saisissez la clé. Les rôles personnalisés combinent une liste fixe de permissions ; un membre ou une invitation peut être limité à certaines apps. Les avoirs couvrent un montant partiel ou total, pas d'autres corrections. L'e-mail est testé contre Mailpit (STARTTLS et identification), les paiements contre stripe-mock, la connexion contre Dex : de vrais serveurs, mais jamais un fournisseur réel ni de l'argent réel.</div>''',
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
<h2>Organizations, pagination, limits</h2>
<ul><li>Everything acts in one organization: your personal workspace by default, or the one named by the <code>X-Org: &lt;id&gt;</code> header (or <code>?org=&lt;id&gt;</code> for plain links such as the PDF). Not a member: 404.</li>
<li>List endpoints (apps, tokens, sessions, activity, admin users) take <code>limit</code> (default 100, max 500) and <code>offset</code> and answer <code>{"…": [...], "total": n, "limit": l, "offset": o}</code>.</li>
<li>Rate limits: 600 requests a minute per signed-in user, 120 per token (<code>429</code> beyond).</li></ul>
<h2>Endpoints</h2>
<table><thead><tr><th>Method and path</th><th>What it does</th></tr></thead><tbody>
<tr><td><code>POST /api/signup</code> · <code>/api/login</code> · <code>/api/logout</code></td><td>Create an account and sign in; sign in; sign out</td></tr>
<tr><td><code>POST /api/password/reset-request</code> · <code>/api/password/reset</code> · <code>/api/password/change</code></td><td>Reset by e-mailed link (always answers the same); change (signs out other sessions)</td></tr>
<tr><td><code>GET /api/me</code> · <code>PATCH /api/me</code> · <code>DELETE /api/me</code> · <code>GET /api/export</code></td><td>Profile; rename; delete the account (password required, no open invoice); export your data</td></tr>
<tr><td><code>POST /api/login/2fa</code></td><td>Second step when two-factor sign-in is on: <code>ticket</code> and <code>code</code> (or a recovery code)</td></tr>
<tr><td><code>POST /api/2fa/setup</code> · <code>/api/2fa/enable</code> · <code>/api/2fa/disable</code></td><td>Two-factor sign-in (browser session only); enable returns eight recovery codes once</td></tr>
<tr><td><code>POST /api/verify</code> · <code>/api/verify/resend</code></td><td>Confirm an e-mail address with the emailed token; send the link again</td></tr>
<tr><td><code>GET</code> · <code>POST /api/orgs</code>; <code>GET</code> · <code>PATCH</code> · <code>DELETE /api/org</code></td><td>Your organizations; create one; the current one (members, pending invitations, billing details); rename or set billing details (admin); delete (owner)</td></tr>
<tr><td><code>POST /api/org/invites</code> · <code>DELETE /api/org/invites/{id}</code> · <code>POST /api/invites/accept</code></td><td>Invite by e-mail with a role; cancel; accept with the emailed token (browser session of the invited address)</td></tr>
<tr><td><code>PATCH</code> · <code>DELETE /api/org/members/{user_id}</code></td><td>Change a role; remove a member (or leave, with your own id)</td></tr>
<tr><td><code>GET /api/invoices/{id}/pdf</code> · <code>/api/credit-notes/{id}/pdf</code></td><td>An invoice or a credit note as a PDF (needs <code>billing.read</code>; numbered documents only)</td></tr>
<tr><td><code>POST /api/org/roles</code> · <code>DELETE /api/org/roles/{name}</code></td><td>Define a custom role from the permission list (never more than you hold); delete one nobody uses</td></tr>
<tr><td><code>GET /api/sso/config</code> · <code>/api/sso/start</code> · <code>/api/sso/callback</code></td><td>Single sign-on with OpenID Connect: whether it is on; redirect to the provider; return from the provider (sets the session cookie and redirects)</td></tr>
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
<tr><td><code>GET /api/admin/overview</code> · <code>/api/admin/users</code> · <code>/api/admin/settings</code> · <code>/api/admin/mail</code></td><td>First account only: totals, users, prices and company, mail queue</td></tr>
<tr><td><code>PUT /api/admin/pricing</code> · <code>/api/admin/company</code> · <code>POST /api/admin/test-mail</code></td><td>First account only: set prices and tax (validated, bounded), company details for invoices, send a test message</td></tr>
<tr><td><code>GET /api/admin/invoices</code> · <code>POST /api/admin/invoices/{id}/credit</code></td><td>First account only: numbered invoices; issue a credit note (<code>amount_usd</code> of the subtotal, <code>reason</code>)</td></tr>
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
<h2>Organisations, pagination, limites</h2>
<ul><li>Tout agit dans une organisation : votre espace personnel par défaut, ou celle désignée par l'en-tête <code>X-Org: &lt;id&gt;</code> (ou <code>?org=&lt;id&gt;</code> pour les liens simples comme le PDF). Pas membre : 404.</li>
<li>Les listes (apps, jetons, sessions, activité, utilisateurs admin) acceptent <code>limit</code> (100 par défaut, 500 au plus) et <code>offset</code> et répondent <code>{"…": [...], "total": n, "limit": l, "offset": o}</code>.</li>
<li>Limites de débit : 600 requêtes par minute et par utilisateur connecté, 120 par jeton (<code>429</code> au-delà).</li></ul>
<h2>Points d'entrée</h2>
<table><thead><tr><th>Méthode et chemin</th><th>Ce que ça fait</th></tr></thead><tbody>
<tr><td><code>POST /api/signup</code> · <code>/api/login</code> · <code>/api/logout</code></td><td>Créer un compte et se connecter ; se connecter ; se déconnecter</td></tr>
<tr><td><code>POST /api/password/reset-request</code> · <code>/api/password/reset</code> · <code>/api/password/change</code></td><td>Réinitialiser par lien envoyé (répond toujours pareil) ; changer (déconnecte les autres sessions)</td></tr>
<tr><td><code>GET /api/me</code> · <code>PATCH /api/me</code> · <code>DELETE /api/me</code> · <code>GET /api/export</code></td><td>Profil ; renommer ; supprimer le compte (mot de passe requis, aucune facture ouverte) ; exporter vos données</td></tr>
<tr><td><code>POST /api/login/2fa</code></td><td>Seconde étape quand la double authentification est active : <code>ticket</code> et <code>code</code> (ou un code de secours)</td></tr>
<tr><td><code>POST /api/2fa/setup</code> · <code>/api/2fa/enable</code> · <code>/api/2fa/disable</code></td><td>Double authentification (session de navigateur seulement) ; enable renvoie huit codes de secours, une fois</td></tr>
<tr><td><code>POST /api/verify</code> · <code>/api/verify/resend</code></td><td>Confirmer une adresse e-mail avec le jeton reçu ; renvoyer le lien</td></tr>
<tr><td><code>GET</code> · <code>POST /api/orgs</code> ; <code>GET</code> · <code>PATCH</code> · <code>DELETE /api/org</code></td><td>Vos organisations ; en créer une ; l'organisation courante (membres, invitations en attente, coordonnées de facturation) ; renommer ou fixer les coordonnées (admin) ; supprimer (propriétaire)</td></tr>
<tr><td><code>POST /api/org/invites</code> · <code>DELETE /api/org/invites/{id}</code> · <code>POST /api/invites/accept</code></td><td>Inviter par e-mail avec un rôle ; annuler ; accepter avec le jeton reçu (session de navigateur de l'adresse invitée)</td></tr>
<tr><td><code>PATCH</code> · <code>DELETE /api/org/members/{user_id}</code></td><td>Changer un rôle ; retirer un membre (ou partir, avec votre propre id)</td></tr>
<tr><td><code>GET /api/invoices/{id}/pdf</code> · <code>/api/credit-notes/{id}/pdf</code></td><td>Une facture ou un avoir en PDF (exige <code>billing.read</code> ; documents numérotés seulement)</td></tr>
<tr><td><code>POST /api/org/roles</code> · <code>DELETE /api/org/roles/{name}</code></td><td>Définir un rôle personnalisé à partir de la liste de permissions (jamais plus que ce que vous détenez) ; supprimer un rôle inutilisé</td></tr>
<tr><td><code>GET /api/sso/config</code> · <code>/api/sso/start</code> · <code>/api/sso/callback</code></td><td>Connexion unique OpenID Connect : si elle est active ; redirection vers le fournisseur ; retour du fournisseur (pose le cookie de session et redirige)</td></tr>
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
<tr><td><code>GET /api/admin/overview</code> · <code>/api/admin/users</code> · <code>/api/admin/settings</code> · <code>/api/admin/mail</code></td><td>Premier compte seulement : totaux, utilisateurs, prix et société, file des messages</td></tr>
<tr><td><code>PUT /api/admin/pricing</code> · <code>/api/admin/company</code> · <code>POST /api/admin/test-mail</code></td><td>Premier compte seulement : fixer prix et taxe (validés, bornés), coordonnées de la société pour les factures, envoyer un message de test</td></tr>
<tr><td><code>GET /api/admin/invoices</code> · <code>POST /api/admin/invoices/{id}/credit</code></td><td>Premier compte seulement : factures numérotées ; émettre un avoir (<code>amount_usd</code> du sous-total, <code>reason</code>)</td></tr>
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

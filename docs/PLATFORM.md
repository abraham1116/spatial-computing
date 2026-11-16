# Console and account service

`spatial platform serve` runs the account service: sign up, sign in, apps linked to the infrastructure, API keys, usage, invoices and payment, with a single-page console in `spatial/platform/static/`.

## What exists
| Part | How |
|---|---|
| Accounts | e-mail and password (scrypt), sessions in SQLite (only a SHA-256 of the cookie token is stored), password change and reset by single-use link, first account is admin |
| Apps | up to 20 per user; each is the hub tenant `appN`; optional monthly budget (test jobs refused when reached) |
| API keys | `client` (`fleet:submit`, `fleet:read`) or `node` (`fleet:report`, `fleet:work`) hub credentials named `appN:kM`, 1 to 365 days, shown once, revocable at once; at most 10 active per app |
| Usage | the hub appends one JSON line per finished task (`--usage-file`); the service ingests it incrementally into SQLite, never reads a half-written line, survives rotation |
| Billing | compute seconds per app, free monthly allowance, price per hour, minimum invoice; invoices created when a month ends; Stripe Checkout and a signed webhook |
| Account tokens | `spt_…` bearer tokens for the REST API (read or write, shown once, hashed in the database, cannot mint tokens, change the password or delete the account) |
| Sessions and activity | list and end sessions, security activity log, password change signs out the others |
| Jobs | a curated catalogue of allow-listed workloads with suggested defaults and hard upper bounds; submitted with a short-lived client credential of the app |
| Fleet view | the user's nodes (those that joined with their node keys), queue counts and recent jobs, read from the hub with a read-only service credential and filtered by tenant |
| Account | rename, export (no secrets), delete (blocked by an open invoice) |
| Admin | first account only: users, totals, hub status, configuration |
| Organizations and roles | every app, key, job, usage and invoice belongs to an organization; four roles (viewer, member, admin, owner) enforced on every call; invitations by e-mail (one address, single use, 7 days); personal workspace per user; at least one owner always remains |
| Custom roles | permissions (`apps.write`, `keys.write`, `jobs.submit`, `billing.read`, `billing.pay`, `org.manage`, `members.manage`, ...) behind the four built-in roles; up to ten custom roles per organization; nobody can define or grant a role with a permission they lack |
| Single sign-on | OpenID Connect: authorization code + PKCE, ID token verified (RS256 signature against the provider's keys, issuer, audience, expiry, nonce, confirmed e-mail), single-use state, domain allow-list, auto-create or existing accounts only; our own 2FA still applies; tested with a local fake provider using real RSA signatures |
| VAT numbers | format for EU, UK, CH, NO; check digit for AT, BE, DE, DK, FR, IT, PL, PT (checked against known real numbers and corrupted ones); optional VIES lookup |
| Credit notes | numbered `CN-...`, PDF, partial or full, tax at the invoice's rate; unpaid invoices shrink, paid ones refund through Stripe or stay `refund_due` |
| Two-factor sign-in | TOTP (RFC 6238, checked against the standard test vector), eight single-use recovery codes, a code works once, five tries per attempt |
| E-mail verification | link at sign-up; enforced for keys, jobs and organizations when SMTP is configured (flag `--require-verified`) |
| Prices and tax | set by the operator in Admin (validated, bounded), stored in the database; invoices keep the prices they were issued with; tax rate by customer country; simplified reverse charge |
| Invoices | gap-free numbers (`INV-2026-00001`), subtotal, tax, total, PDF (own minimal writer), billing details per organization, waived below the minimum |
| E-mail queue | SMTP (STARTTLS or TLS) with retries and backoff; visible in Admin; test message |
| Limits | 600 requests/min per user, 120 per token; pagination on lists |
| Console | Overview (checklist), Apps (tabs: Overview, Keys, Connect, Jobs, Settings), Jobs, Fleet, API keys, Team, Usage & billing, Settings (Profile, Security with two-factor and sessions, Account tokens, Activity, Data), Admin (prices and tax, company, e-mail), sign in / up / reset; REST API in [site docs](../site/docs/api.html) |

## Run it
```bash
spatial token init --master-key-file hub.key
spatial serve hub --master-key-file hub.key --port 7700 --usage-file usage.jsonl --revoked-file revoked.txt
spatial platform serve --master-key-file hub.key --hub 127.0.0.1:7700 --usage-file usage.jsonl --revoked-file revoked.txt
# open http://127.0.0.1:8090/ , create an account, an app, a node key and a client key
spatial agent --hub 127.0.0.1:7700 --token-file node.tok
spatial fleet submit --hub 127.0.0.1:7700 --token-file client.tok --workload montecarlo_pi --params '{"samples":1000000}'
```
The hub, the platform and the files must share the master key, the usage file and the revoked file (same host or a shared volume). Production layout: [DEPLOY.md](DEPLOY.md).

## Verified (tests/test_platform.py and test_platform2.py, 33 tests, plus a driven browser session)
- A key issued by the console is accepted by a real hub; a node key runs work; a client key submits; a client cannot impersonate a node; the hub meters the work to the right app; another user sees no usage; revoking a key stops it on the running hub through the revoked file.
- Wrong passwords: same message for known and unknown accounts, lock after 5, lock lifts after 15 minutes; reset reveals nothing about accounts; a reset link works once; changing a password signs out other sessions.
- HTTP: cookie flags, CSRF token and same-origin check, 401 without a session, 404 (not 403) for another user's app, body limit, strict CSP, no path traversal.
- Billing: free allowance shared by the account, invoices created once per month, tiny amounts waived, payment refused without a provider, webhook signature checked, forged and late webhooks rejected, a paid webhook applied once.
- A real session in headless Chrome: sign up, create an app and two keys, wrong password, sign in, run a test job on the hub through an agent that joined with the node key, see usage, billing, settings.

- Two-factor sign-in, the organization switcher, invitations, e-mail verification and the operator's price form were also driven in a real browser session (headless Chrome): a second user joined an organization through an e-mailed link, verified their address, and the operator signed in again with a TOTP code.

## Not done
- Tax is a rate table, a simplified reverse-charge switch, VAT-number checks, credit notes, a required-fields checklist for seven countries (FR, DE, ES, IT, NL, BE, GB) and UBL 2.1 XML export. It is not a tax-compliance engine: the checklist covers commonly listed fields, not every rule; the UBL files pass the official XSD but not the Peppol Schematron rules and are not transmitted anywhere (no Peppol access point, Chorus Pro or Factur-X). Have an accountant check it.
- No SAML, on purpose: a SAML parser and signature verifier written here would be a security risk. Put an OpenID Connect broker (Dex, Keycloak) in front of your SAML identity provider. OpenID Connect is tested against a real provider (Dex) but not against Google, Entra or Okta. Per-app scoping exists for members and invitations; custom roles themselves are organization-wide. One service process with SQLite.
- Real-server tests cover Mailpit (SMTP with STARTTLS and login), stripe-mock and Dex. Not covered: a live Stripe account with real money, a production mail relay, a hosted identity provider.
- Hosting: `--embedded-hub` runs console and hub in one process. `deploy/fly.toml` and `deploy/render.yaml` are templates nobody has deployed; the console has no public instance run by us.
- The QR code encoder (byte mode, level M, versions 1 to 10) is checked module for module against the `qrcode` library; the automatic mask choice differs from that library's in some cases, which is valid QR but not identical.
- E-mail was tested against a local SMTP stand-in, not a real provider; payments against a fake Stripe API only; the default price list is an example until the operator saves real prices.
- Sessions last 7 days with no refresh. API tokens are per user (they act in whichever organization the `X-Org` header names, if the user belongs to it).

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
| Console | Overview (checklist), Apps (tabs: Overview, Keys, Connect, Jobs, Settings), Jobs, Fleet, API keys, Usage & billing, Settings (Profile, Security, Account tokens, Activity, Data), Admin, sign in / up / reset; REST API in [site docs](../site/docs/api.html) |

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

## Verified (tests/test_platform.py, 18 tests, plus a driven browser session)
- A key issued by the console is accepted by a real hub; a node key runs work; a client key submits; a client cannot impersonate a node; the hub meters the work to the right app; another user sees no usage; revoking a key stops it on the running hub through the revoked file.
- Wrong passwords: same message for known and unknown accounts, lock after 5, lock lifts after 15 minutes; reset reveals nothing about accounts; a reset link works once; changing a password signs out other sessions.
- HTTP: cookie flags, CSRF token and same-origin check, 401 without a session, 404 (not 403) for another user's app, body limit, strict CSP, no path traversal.
- Billing: free allowance shared by the account, invoices created once per month, tiny amounts waived, payment refused without a provider, webhook signature checked, forged and late webhooks rejected, a paid webhook applied once.
- A real session in headless Chrome: sign up, create an app and two keys, wrong password, sign in, run a test job on the hub through an agent that joined with the node key, see usage, billing, settings.

## Not done
No teams or roles, no two-factor authentication, no pagination in the API, no e-mail verification at sign-up, no taxes or PDF invoices, no admin console, no per-key rate limits (only the hub's quotas, which live in memory), a single process with SQLite. Payments were tested against a fake Stripe API only. The default price list is an example. Sessions last 7 days with no refresh. E-mail needs SMTP settings; without them messages stay in the `outbox` table.

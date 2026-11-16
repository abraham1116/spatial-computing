# Deploying the platform

## One server with Docker
```bash
cp deploy/.env.example deploy/.env        # set DOMAIN (DNS A record to this server), HUB_PUBLIC_ADDR, optional Stripe and SMTP
docker compose run --rm init              # once: creates the hub master key in the data volume
cp my-pricing.json ...                    # optional: put your price list in the data volume as /data/pricing.json
docker compose --env-file deploy/.env up -d --build
```
Services: `hub` (fleet hub on port 7700), `platform` (console and API, internal port 8090), `caddy` (HTTPS with an automatic certificate, ports 80 and 443). One image (`Dockerfile`) runs as a non-root user and keeps everything in the `data` volume.

Open to the internet: 80 and 443 (console) and 7700 (agents and API clients; SWP/2 is authenticated and encrypted). Restrict 7700 to the networks that need it.

## Stripe
Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in `deploy/.env`; in the Stripe dashboard add a webhook to `https://DOMAIN/api/billing/webhook` for `checkout.session.completed`. Use test keys first. Prices: `/data/pricing.json` (`free_compute_hours_per_month`, `compute_usd_per_hour`, `min_invoice_usd`, `currency`).

## Backups
`deploy/backup.sh` copies a consistent snapshot of the account database and the hub state. The hub master key is not in it: it can issue any credential, store it separately (a password manager or secret store) and rotate it by re-issuing keys.

## Checked here / not checked here
- Checked: the console, hub and agent run together on one machine (see PLATFORM.md); the image builds and the compose services start under Docker (Colima) on this Mac, see the result in the changelog.
- Not checked: a public server, TLS issuance by Caddy, real Stripe, real SMTP, load, upgrades with data in the volume. The compose file is a starting point, not a hardened reference: add monitoring, off-site backups and a firewall.

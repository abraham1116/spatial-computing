# Live GPU market prices

`spatial.market` reads real, current prices from Vast.ai's public GPU marketplace — the same
data their own search page shows a logged-out visitor. No API key, no account, no rented
hardware, no money spent: this module only reads.

```bash
spatial market --gpu H100
spatial market --gpu H100 --neocloud-usd-per-hour 4.0        # arbitrage spread against your own reference price
spatial market --vertical render --neocloud-usd-per-hour 1.5 # a preset list of GPUs instead of one chip
```

```python
from spatial.market import fetch_offers, cheapest, cheapest_for, spread_vs, spread_for, VERTICALS
offers = fetch_offers()
cheapest(offers, "H100")                                # the cheapest reliable (>= 0.5) H100 listing right now
spread_vs(offers, "H100", neocloud_usd_per_hour=4.0)     # {"market_usd_h", "neocloud_usd_h", "spread_usd_h", "spread_pct", "offer"}
cheapest_for(offers, "render")                            # cheapest among VERTICALS["render"] (RTX 4090/5090/PRO 6000/A6000...)
spread_for(offers, "render", neocloud_usd_per_hour=1.5)
```

## Verticals

Same pattern as the `pk_rtb`/`pk_credit`/... presets over `batch_score` (`spatial.kernel`): a
name over the SAME mechanism (`cheapest_among`/`spread_among`), never a different algorithm —
only the list of GPU names differs. Today: `VERTICALS["render"]` groups the cards 3D rendering
and VFX render farms are commonly priced against (RTX 4090/5090/4080/5080, RTX PRO 6000/5000,
RTX A6000, RTX 6000 Ada) — consumer/prosumer cards, not the datacenter chips (H100/A100/B200)
the rest of this module defaults to.

## What this proves, and what it does not

This turns the GPU arbitrage pricing idea into something checkable against live numbers instead
of a hypothesis on paper: on 17 November 2026 the cheapest reliable H100 on Vast.ai was
**2.336 $/h** against a commonly cited "neocloud" (RunPod/Lambda) price of 4-6 $/h — a real,
live spread, not a cited blog figure.

**It does not prove we can capture that spread.** Reading a price is free and instant; actually
renting that GPU, running a real job on it, and reselling the result is a separate, later step
that needs an account on the marketplace, spends real money, and needs the user's explicit
go-ahead each time — nothing in this module does any of that.

## Limits

- One marketplace (Vast.ai). RunPod's equivalent catalog endpoint needs an API key (confirmed:
  an unauthenticated request returns HTTP 401), so it is not read here; a key could be added later.
- The public `/bundles/` endpoint returned 64 offers in one real test run on 17 November 2026 —
  likely a capped or sampled view, not Vast.ai's full live inventory (their authenticated search
  may show more). Not confirmed against their own documentation.
- `reliability` is Vast.ai's own host score, not independently verified by us.
- No historical prices, no price alerts, no automatic rental: a single, real, point-in-time read.

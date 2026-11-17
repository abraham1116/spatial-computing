"""Vast.ai's public GPU marketplace: a real, live, read-only price feed. No API key is used or
needed for this endpoint (it is the same data their own search page shows a logged-out visitor);
we never authenticate, never bid, never rent. One real network call per `fetch_offers()`."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

BUNDLES_URL = "https://console.vast.ai/api/v0/bundles/"


class MarketError(Exception):
    """The marketplace could not be reached or its response could not be understood. Never
    silently replaced by a stale or made-up price: callers see this and decide what to do."""


@dataclass(frozen=True)
class Offer:
    gpu_name: str
    num_gpus: int
    gpu_frac: float          # fraction of ONE physical GPU this listing gives you (1.0 = a whole GPU)
    usd_per_hour: float      # dph_total: Vast.ai's own all-in price for this listing (their fee included)
    reliability: float       # Vast.ai's own 0..1 host score; not independently verified here
    geolocation: str

    @property
    def usd_per_hour_per_gpu(self) -> float:
        """Normalised to one whole GPU, so a fractional/shared listing compares fairly with a
        dedicated one (a listing with gpu_frac 0.25 at $0.21/h is $0.86/h for a whole GPU)."""
        return self.usd_per_hour / self.gpu_frac if self.gpu_frac else self.usd_per_hour


def parse_offers(data: dict) -> list[Offer]:
    """`data` is the parsed JSON body of a GET to BUNDLES_URL (or a fixture of the same shape,
    for tests: no network, no live prices, see tests/data/vast_bundles_sample.json)."""
    out = []
    for o in data.get("offers") or []:
        try:
            out.append(Offer(
                gpu_name=str(o["gpu_name"]), num_gpus=int(o["num_gpus"]), gpu_frac=float(o.get("gpu_frac") or 1.0),
                usd_per_hour=float(o["dph_total"]), reliability=float(o.get("reliability") or 0.0),
                geolocation=str(o.get("geolocation") or "?")))
        except (KeyError, TypeError, ValueError):
            continue           # one malformed listing is skipped, not a reason to fail the whole fetch
    return out


def fetch_offers(timeout_s: float = 15.0) -> list[Offer]:
    """A real network call to Vast.ai's public marketplace endpoint. Raises MarketError on any
    failure (network, non-200, malformed JSON) instead of returning stale or fabricated data."""
    req = urllib.request.Request(BUNDLES_URL, headers={"Accept": "application/json", "User-Agent": "spatial-computing-market/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            if r.status != 200:
                raise MarketError(f"Vast.ai returned HTTP {r.status}")
            data = json.loads(r.read())
    except MarketError:
        raise
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        raise MarketError(f"could not reach or parse Vast.ai's marketplace ({type(e).__name__}: {e})") from e
    return parse_offers(data)


def cheapest(offers: list[Offer], gpu_name_contains: str, min_reliability: float = 0.5) -> Offer | None:
    """The lowest per-whole-GPU price among offers whose name contains `gpu_name_contains`
    (case-insensitive) and whose reliability is at least `min_reliability` (default 0.5: an
    unreliable host is not a fair price to quote as THE price). None if nothing matches."""
    cand = [o for o in offers if gpu_name_contains.lower() in o.gpu_name.lower() and o.reliability >= min_reliability]
    return min(cand, key=lambda o: o.usd_per_hour_per_gpu) if cand else None


def spread_vs(offers: list[Offer], gpu_name_contains: str, neocloud_usd_per_hour: float,
              min_reliability: float = 0.5) -> dict | None:
    """The arbitrage spread: the gap between the cheapest sufficiently-reliable marketplace price
    for this GPU and a 'neocloud'/list price the CALLER supplies (never invented here). None if no
    offer matches. `min_reliability` defaults to 0.5: an unreliable host is not a fair price to quote."""
    c = cheapest(offers, gpu_name_contains, min_reliability)
    if c is None:
        return None
    spread = neocloud_usd_per_hour - c.usd_per_hour_per_gpu
    return {"market_usd_h": c.usd_per_hour_per_gpu, "neocloud_usd_h": neocloud_usd_per_hour,
            "spread_usd_h": spread, "spread_pct": (spread / neocloud_usd_per_hour * 100) if neocloud_usd_per_hour else None,
            "offer": c}

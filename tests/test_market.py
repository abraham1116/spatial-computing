"""Live GPU market prices (spatial.market): parsing tested against a frozen real sample, no
network; one test makes a REAL call to Vast.ai's public marketplace and skips gracefully if it
cannot be reached (CI network policy, outage, or the endpoint changing shape)."""
import json
from pathlib import Path

import pytest

from spatial.market import MarketError, cheapest, fetch_offers, parse_offers, spread_vs

FIXTURE = json.loads((Path(__file__).parent / "data" / "vast_bundles_sample.json").read_text())


def test_parse_offers_reads_a_real_sample_shape():
    offers = parse_offers(FIXTURE)
    assert len(offers) == 10
    names = {o.gpu_name for o in offers}
    assert "H100 NVL" in names and "RTX 4090" in names
    h100 = [o for o in offers if o.gpu_name == "H100 NVL"]
    assert len(h100) == 2 and {round(o.reliability, 3) for o in h100} == {0.998, 0.2}


def test_parse_offers_skips_a_malformed_listing_instead_of_failing():
    bad = {"offers": [{"gpu_name": "X"}, {"gpu_name": "RTX 4090", "num_gpus": 1, "dph_total": 0.5, "gpu_frac": 1.0, "reliability": 0.9, "geolocation": "?"}]}
    offers = parse_offers(bad)
    assert len(offers) == 1 and offers[0].gpu_name == "RTX 4090"
    assert parse_offers({}) == [] and parse_offers({"offers": None}) == []


def test_usd_per_hour_per_gpu_normalises_a_fractional_listing():
    offers = parse_offers(FIXTURE)
    frac = next(o for o in offers if o.gpu_frac == 0.25)
    assert frac.usd_per_hour_per_gpu == pytest.approx(frac.usd_per_hour / 0.25)
    whole = next(o for o in offers if o.gpu_frac == 1.0)
    assert whole.usd_per_hour_per_gpu == whole.usd_per_hour


def test_cheapest_excludes_low_reliability_offers_by_default():
    offers = parse_offers(FIXTURE)
    c = cheapest(offers, "H100")
    assert c is not None and c.reliability == pytest.approx(0.998)       # the $1.50/h, reliability-0.2 listing is excluded
    c_any = cheapest(offers, "H100", min_reliability=0.0)
    assert c_any.reliability == pytest.approx(0.2)                       # with the filter open, the cheaper-but-unreliable one wins
    assert cheapest(offers, "no such gpu") is None


def test_spread_vs_computes_the_arbitrage_gap_against_a_caller_supplied_price():
    offers = parse_offers(FIXTURE)
    r = spread_vs(offers, "H100", neocloud_usd_per_hour=4.0)
    assert r["market_usd_h"] == pytest.approx(2.336)
    assert r["spread_usd_h"] == pytest.approx(4.0 - 2.336)
    assert r["spread_pct"] == pytest.approx((4.0 - 2.336) / 4.0 * 100)
    assert r["offer"].gpu_name == "H100 NVL"
    assert spread_vs(offers, "no such gpu", 4.0) is None
    assert spread_vs(offers, "H100", 0.0) is not None and spread_vs(offers, "H100", 0.0)["spread_pct"] is None  # no division by zero


def _vast_reachable():
    try:
        fetch_offers(timeout_s=5.0)
        return True
    except MarketError:
        return False


@pytest.mark.skipif(not _vast_reachable(), reason="Vast.ai's public marketplace is not reachable from here right now")
def test_fetch_offers_is_a_real_live_call_with_plausible_prices():
    offers = fetch_offers()
    assert len(offers) > 0
    assert all(o.usd_per_hour >= 0 and 0.0 <= o.reliability <= 1.0 for o in offers)
    gpu_names = {o.gpu_name for o in offers}
    assert any("RTX" in n or "A100" in n or "H100" in n or "L4" in n or "4090" in n for n in gpu_names)   # a real marketplace, not an empty shell

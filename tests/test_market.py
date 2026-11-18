"""Live GPU market prices (spatial.market): parsing tested against a frozen real sample, no
network; one test makes a REAL call to Vast.ai's public marketplace and skips gracefully if it
cannot be reached (CI network policy, outage, or the endpoint changing shape)."""
import json
from pathlib import Path

import pytest

from spatial.market import VERTICALS, MarketError, cheapest, cheapest_among, cheapest_for, fetch_offers, parse_offers, spread_among, spread_for, spread_vs

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


def test_cheapest_among_matches_any_of_several_gpu_names():
    offers = parse_offers(FIXTURE)
    c = cheapest_among(offers, ("RTX 4090", "RTX 5090"))
    assert c is not None and c.gpu_name in ("RTX 4090", "RTX 5090", "RTX 4090D")   # substring match: "RTX 4090" also matches "RTX 4090D"
    assert cheapest_among(offers, ("no such gpu",)) is None


@pytest.mark.parametrize("vertical", ["render", "cloud_gaming"])
def test_vertical_is_the_same_mechanism_as_cheapest_among(vertical):
    offers = parse_offers(FIXTURE)
    assert vertical in VERTICALS and len(VERTICALS[vertical]) > 1
    direct = cheapest_among(offers, VERTICALS[vertical])
    via_name = cheapest_for(offers, vertical)
    assert direct == via_name       # cheapest_for(vertical) is NOT a different algorithm, just this preset
    with pytest.raises(MarketError, match="unknown vertical"):
        cheapest_for(offers, "no-such-vertical")


def test_cloud_gaming_and_render_verticals_both_target_gaming_tier_cards_not_datacenter_chips():
    for name in VERTICALS["cloud_gaming"] + VERTICALS["render"]:
        assert "RTX" in name and "H100" not in name and "A100" not in name and "B200" not in name


@pytest.mark.parametrize("vertical", ["render", "cloud_gaming"])
def test_spread_for_matches_spread_among_the_same_preset(vertical):
    offers = parse_offers(FIXTURE)
    a = spread_among(offers, VERTICALS[vertical], neocloud_usd_per_hour=1.5)
    b = spread_for(offers, vertical, neocloud_usd_per_hour=1.5)
    assert a == b
    with pytest.raises(MarketError, match="unknown vertical"):
        spread_for(offers, "no-such-vertical", 1.5)


# One real network call for the whole module (not one per test): avoids the flakiness of hitting
# a live third-party endpoint twice in quick succession, which happened in practice (TLS handshake
# timeouts under load). Every "live" assertion below reuses this single fetch.
try:
    _LIVE_OFFERS = fetch_offers(timeout_s=20.0)
except MarketError:
    _LIVE_OFFERS = None

needs_live_market = pytest.mark.skipif(_LIVE_OFFERS is None, reason="Vast.ai's public marketplace is not reachable from here right now")


@needs_live_market
def test_fetch_offers_is_a_real_live_call_with_plausible_prices():
    offers = _LIVE_OFFERS
    assert len(offers) > 0
    assert all(o.usd_per_hour >= 0 and 0.0 <= o.reliability <= 1.0 for o in offers)
    gpu_names = {o.gpu_name for o in offers}
    assert any("RTX" in n or "A100" in n or "H100" in n or "L4" in n or "4090" in n for n in gpu_names)   # a real marketplace, not an empty shell


@needs_live_market
@pytest.mark.parametrize("vertical", ["render", "cloud_gaming"])
def test_vertical_finds_a_real_live_offer(vertical):
    c = cheapest_for(_LIVE_OFFERS, vertical)
    if c is not None:                                        # a real marketplace can genuinely have none in stock right now
        assert c.usd_per_hour_per_gpu > 0 and c.reliability >= 0.5

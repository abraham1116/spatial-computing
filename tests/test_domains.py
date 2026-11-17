"""First components of the non-priority domains (the AI planner tests live in the private repo). These tests prove the small pieces
that exist; they are not evidence that the domains are operational products."""
import pytest

from spatial.intelligence import PowerLawPredictor


def test_intelligence_predictor_recovers_power_law():
    p = PowerLawPredictor()
    for w in (1e3, 1e4, 1e5):
        p.observe("fast", w, 2e-8 * w ** 1.0)
        p.observe("slow", w, 5e-6 * w ** 1.0)
        p.observe("startup_heavy", w, 0.5 + 1e-9 * w)
    assert p.predict("fast", 1e6) == pytest.approx(2e-2, rel=1e-6)
    assert p.best(1e6)[0] == "fast"
    assert p.predict("unknown", 10) is None

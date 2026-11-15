"""First components of the non-priority domains (the AI planner tests live in the private repo). These tests prove the small pieces
that exist; they are not evidence that the domains are operational products."""
import numpy as np
import pytest

from spatial.holographic import LightFieldSpec, voxelize
from spatial.intelligence import PowerLawPredictor
from spatial.scientific import JobSpec, black_scholes_call, european_call_mc, run_job
from spatial.simulation import simulate


def test_scientific_job_validates_against_closed_form():
    args = dict(s0=100.0, k=105.0, r=0.03, sigma=0.2, t=1.0)
    ref = black_scholes_call(**args)
    job = JobSpec("eu_call_mc", "finance", lambda: european_call_mc(paths=400_000, seed=1, **args), reference=ref)
    m = run_job(job)
    assert m.ok and abs(m.metrics["value"] - ref) < 0.05
    bad = JobSpec("wrong_ref", "finance", lambda: european_call_mc(paths=400_000, seed=1, **args), reference=ref + 1)
    assert not run_job(bad).ok                                 # validation really fails when wrong


def test_simulation_conserves_heat_and_backends_agree():
    u0 = np.zeros((40, 40))
    u0[18:22, 18:22] = 100.0
    a = simulate(u0, 0.2, 200, "numpy")
    b = simulate(u0, 0.2, 200, "numba")
    assert np.allclose(a, b, atol=1e-9)
    assert a.sum() == pytest.approx(u0.sum(), rel=1e-9)        # insulated borders
    assert a.max() < u0.max()
    with pytest.raises(ValueError):
        simulate(u0, 0.3, 1)


def test_intelligence_predictor_recovers_power_law():
    p = PowerLawPredictor()
    for w in (1e3, 1e4, 1e5):
        p.observe("fast", w, 2e-8 * w ** 1.0)
        p.observe("slow", w, 5e-6 * w ** 1.0)
        p.observe("startup_heavy", w, 0.5 + 1e-9 * w)
    assert p.predict("fast", 1e6) == pytest.approx(2e-2, rel=1e-6)
    assert p.best(1e6)[0] == "fast"
    assert p.predict("unknown", 10) is None


def test_holographic_data_model_only():
    pts = np.array([[0, 0, 0], [0.9, 0.9, 0.9], [0.1, 0.1, 0.1]])
    g = voxelize(pts, 0.5)
    assert g.occupancy.shape == (2, 2, 2) and g.filled == 2
    lf = LightFieldSpec(views_x=45, views_y=1, width=1536, height=2048, fps=60)
    assert lf.raw_bytes_per_second == 45 * 1536 * 2048 * 60 * 3
    assert lf.vs_2d() == pytest.approx(45 * 1536 * 2048 / (3840 * 2160))

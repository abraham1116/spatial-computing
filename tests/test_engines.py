"""One real, verified component per non-core engine: AI, scientific, simulation, intelligence, holographic."""
import numpy as np
import pytest

from spatial.ai import ToyTransformer, measure_restore_vs_recompute
from spatial.compute import detect_node
from spatial.compute.scheduler import ComputeScheduler
from spatial.core.ledger import Ledger
from spatial.holographic import hologram, max_diffraction_angle, reconstruct
from spatial.memory import FileBackend, TieredStore
from spatial.scientific import JobSpec, harmonic_rk4, run_job
from spatial.simulation import nbody


def test_ai_kv_cache_restore_equals_recompute_and_is_measured(tmp_path):
    m = ToyTransformer(layers=3, d=48, heads=4)
    rng = np.random.default_rng(0)
    prefix, tail = rng.integers(0, 256, 300), rng.integers(0, 256, 5)
    full, _ = m.forward(np.concatenate([prefix, tail]))
    _, cache = m.forward(prefix)
    cont, _ = m.forward(tail, cache)
    assert np.allclose(full, cont, atol=1e-3)                       # cached continuation = full recompute
    st = TieredStore(1 << 16, 1 << 16, FileBackend(str(tmp_path / "kv")), codec_name="lz4")   # cache spills to the far tier
    r = measure_restore_vs_recompute(m, prefix, st)
    again, _ = m.forward(tail, r["restored"])
    assert np.allclose(full, again, atol=1e-3)                      # through the tiered store too
    assert r["cache_bytes"] == 3 * 2 * 300 * 48 * 4 and r["recompute_s"] > 0 and r["restore_s"] > 0
    assert st.stats()["far_bytes"] > 0
    st.close()


def test_scientific_ode_job_validates_and_fails_when_wrong():
    exact = float(np.cos(2.0 * 10.0))
    ok = run_job(JobSpec("harmonic_rk4", "engineering", lambda: harmonic_rk4(2.0, 10.0, 4000), reference=exact))
    assert ok.ok and abs(ok.metrics["value"] - exact) < 1e-8
    coarse = run_job(JobSpec("too_coarse", "engineering", lambda: (harmonic_rk4(2.0, 10.0, 12)[0], 1e-9), reference=exact))
    assert not coarse.ok


def test_simulation_nbody_conserves_energy_and_momentum():
    rng = np.random.default_rng(1)
    pos, vel, mass = rng.normal(size=(12, 3)), rng.normal(size=(12, 3)) * 0.1, rng.uniform(0.5, 1.5, 12)
    e0, p0 = nbody.energy(pos, vel, mass, 0.05), (mass[:, None] * vel).sum(0)
    p, v = nbody.leapfrog(pos, vel, mass, dt=1e-3, steps=400, soft=0.05)
    assert abs(nbody.energy(p, v, mass, 0.05) - e0) / abs(e0) < 1e-3
    assert np.allclose((mass[:, None] * v).sum(0), p0, atol=1e-9)
    assert not np.allclose(p, pos)


def test_intelligence_predicts_the_strategy_the_measurements_then_confirm(tmp_path):
    s = ComputeScheduler(detect_node(), Ledger(tmp_path / "l.jsonl"))
    s.warmup()
    assert s.predict_best(300, 100) is None                         # no history yet
    keep = {"multiprocess_numba", "multiprocess_warm_pool"}
    for n in (120, 240):
        s.compare("hist", {"n": n, "iters": 100}, s.mandel_strategies(), skip=keep)
    name, secs = s.predict_best(480, 100)
    rows = s.compare("check", {"n": 480, "iters": 100}, s.mandel_strategies(), skip=keep)
    by = {r.strategy: r.wall_s for r in rows}
    assert name.startswith("local_numba") and by[name] < by["local_numpy"] < by["local_python"]
    assert secs == pytest.approx(by[name], rel=3.0)                 # same order of magnitude
    s.close()


def test_holographic_hologram_reconstructs_its_point_sources():
    wl, pitch, n = 633e-9, 8e-6, 256
    pts = np.array([[0.0, 0.0, 0.05], [3.2e-4, -2.4e-4, 0.05]])
    H = hologram(pts, np.array([1.0, 1.0]), n, pitch, wl)
    img = reconstruct(H, 0.05, pitch, wl)
    peaks = {tuple(int(v) for v in np.unravel_index(i, img.shape)) for i in np.argsort(img.ravel())[-2:]}
    want = {(n // 2 + round(y / pitch), n // 2 + round(x / pitch)) for x, y, _ in pts}
    assert peaks == want                                            # focus lands on the emitters
    blurred = reconstruct(H, 0.08, pitch, wl)                       # wrong depth: energy is spread out
    assert blurred.max() < 0.5 * img.max()
    assert max_diffraction_angle(8e-6, wl) < np.radians(3) < np.radians(20) < max_diffraction_angle(0.9e-6, wl)

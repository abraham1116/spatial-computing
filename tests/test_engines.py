"""One real, verified component per non-core engine: AI, intelligence."""
import numpy as np
import pytest

from spatial.ai import ToyTransformer, measure_restore_vs_recompute
from spatial.compute import detect_node
from spatial.compute.scheduler import ComputeScheduler
from spatial.core.ledger import Ledger
from spatial.memory import FileBackend, TieredStore


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

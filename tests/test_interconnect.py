"""Virtual interconnect: collectives are correct for every algorithm and rank count, run over the
encrypted transport in separate processes, and the cost model behaves like the theory it comes from."""
import math

import pytest

from spatial.interconnect import choose, fit_link, launch, predict
from spatial.interconnect import tasks


@pytest.mark.parametrize("n,algo", [(2, "ring"), (3, "ring"), (4, "ring"), (2, "halving_doubling"), (4, "halving_doubling"),
                                    (2, "tree"), (3, "tree"), (4, "tree"), (5, "tree")])
def test_allreduce_equals_the_exact_sum_for_every_algorithm_and_rank_count(n, algo):
    for elems in (1, 7, 1000):                                    # smaller than the rank count, odd, and bigger
        errs = launch(n, tasks.check_allreduce, algo, elems)
        assert max(errs) < 1e-4, (n, algo, elems, errs)


def test_halving_doubling_refuses_non_power_of_two():
    with pytest.raises(RuntimeError, match="power-of-two"):
        launch(3, tasks.check_allreduce, "halving_doubling", 16)
    assert predict("halving_doubling", 3, 1e6, 1e-4, 1e9) == math.inf


def test_cost_model_matches_the_textbook_formulas_and_crossovers():
    a, b = 1e-4, 1e9                                              # 100 us, 1 GB/s
    # tiny message, many ranks: latency decides -> logarithmic algorithms beat the ring
    assert choose(16, 64, a, b)[0] in ("halving_doubling", "tree")
    assert predict("ring", 16, 64, a, b) > 3.7 * predict("halving_doubling", 16, 64, a, b)   # 2(N-1) latency terms against 2 log2 N: 30 / 8
    # huge message: bandwidth decides -> ring and halving_doubling tie, the tree (full message each step) loses
    t = {k: predict(k, 8, 1e9, a, b) for k in ("ring", "halving_doubling", "tree")}
    assert t["tree"] > 2 * t["ring"] and t["halving_doubling"] <= t["ring"]
    assert choose(6, 1e9, a, b)[0] == "ring"                      # not a power of two: halving_doubling is excluded
    assert predict("ring", 1, 1e9, a, b) == 0
    assert predict("ring", 2, 1e6, a, b) == pytest.approx(2 * a + 1.0 * 1e6 / b)


def test_link_fit_recovers_alpha_and_beta():
    a, b = 2e-4, 5e8
    alpha, beta = fit_link([(s, a + s / b) for s in (64, 1 << 16, 1 << 20, 8 << 20)])
    assert alpha == pytest.approx(a, rel=1e-3) and beta == pytest.approx(b, rel=1e-3)


def test_measured_link_and_prediction_are_in_the_right_order_of_magnitude_on_this_machine():
    out = launch(4, tasks.bench_all, (256, 1 << 18), ("ring", "halving_doubling", "tree"), 3)[0]
    assert out["alpha_s"] > 0 and out["beta_Bps"] > 1e6                          # a real link: at least MB/s
    for row in out["rows"]:
        for algo, meas in row["measured_s"].items():
            pred = row["predicted_s"][algo]
            assert 0.1 < meas / pred < 10, (algo, row["bytes"], meas, pred)       # same order of magnitude

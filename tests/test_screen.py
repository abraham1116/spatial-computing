"""Fleet screening: faults are INJECTED here; no real hardware fault was ever observed."""
import numpy as np
import pytest

from spatial.fabric import metal
from spatial.kernel.library import collatz
from spatial.verify import VerificationError, screen, screen_kernel

needs_metal = pytest.mark.skipif(not metal.available(), reason="no Metal")


def good():
    return np.arange(16, dtype="uint32").reshape(4, 4)


def flipped():
    a = good()
    a[2, 1] ^= 1
    return a


class FakeClock:
    """Returns scripted instants, so timing tests do not depend on the machine."""
    def __init__(self, *durations):
        self.t, self.queue = 0.0, list(durations)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls % 2 == 0:                               # end of an executor: advance by its scripted duration
            self.t += self.queue.pop(0)
        return self.t


def test_all_agree_is_healthy():
    r = screen({"a": good, "b": good, "c": good})
    assert r.healthy and not r.outliers and r.majority is not None
    assert [x.status for x in r.results] == ["ok", "ok", "ok"]


def test_one_corrupted_executor_among_three_is_named():
    r = screen({"gpu0": good, "gpu1": flipped, "gpu2": good})
    assert not r.healthy and r.outliers == ("gpu1",)
    assert {x.name: x.status for x in r.results} == {"gpu0": "ok", "gpu1": "outlier", "gpu2": "ok"}
    assert "gpu1" in r.reason


def test_two_that_disagree_cannot_name_the_culprit():
    r = screen({"a": good, "b": flipped})
    assert not r.healthy and r.outliers == () and r.majority is None
    assert {x.status for x in r.results} == {"undetermined"}
    assert "nobody can tell" in r.reason


def test_three_different_answers_have_no_majority():
    def other():
        return good() + 1
    r = screen({"a": good, "b": flipped, "c": other})
    assert not r.healthy and r.majority is None and r.outliers == ()


def test_a_tie_is_not_a_majority():
    r = screen({"a": good, "b": good, "c": flipped, "d": flipped})
    assert not r.healthy and r.majority is None


def test_a_crashing_executor_is_reported_not_raised():
    def boom():
        raise RuntimeError("ECC error")
    r = screen({"a": good, "b": good, "c": boom})
    assert not r.healthy and r.errors == ("c",)
    assert "RuntimeError: ECC error" in r.results[2].error
    assert r.majority is not None


def test_every_executor_failing():
    def boom():
        raise RuntimeError("x")
    r = screen({"a": boom, "b": boom})
    assert not r.healthy and r.majority is None and "every executor failed" in r.reason


def test_a_straggler_is_flagged_against_the_median():
    r = screen({"a": good, "b": good, "c": good}, clock=FakeClock(1.0, 1.1, 5.0))
    assert not r.healthy and r.stragglers == ("c",) and r.outliers == ()
    assert "slow" in r.reason


def test_tiny_timing_differences_are_not_stragglers():
    r = screen({"a": good, "b": good, "c": good}, clock=FakeClock(0.001, 0.001, 0.004))
    assert r.healthy and r.stragglers == ()


def tagged(kind):
    def run():
        return good()
    run.kind = kind
    return run


def test_a_slow_gpu_is_not_a_straggler_against_fast_cpus():
    """The CI failure on macOS: Metal slower than the median of two CPU runs is a different kind of device."""
    r = screen({"cpu#0": tagged("cpu"), "cpu#1": tagged("cpu"), "metal": tagged("metal")}, clock=FakeClock(0.005, 0.005, 0.5))
    assert r.healthy and r.stragglers == ()


def test_stragglers_are_judged_within_their_own_kind():
    ex = {"c0": tagged("cpu"), "c1": tagged("cpu"), "c2": tagged("cpu"), "g0": tagged("gpu")}
    r = screen(ex, clock=FakeClock(1.0, 1.1, 5.0, 9.0))
    assert r.stragglers == ("c2",)


def test_stragglers_need_three_executors():
    r = screen({"a": good, "b": good}, clock=FakeClock(1.0, 9.0))
    assert r.healthy and r.stragglers == ()


def test_dtype_and_shape_matter_for_the_digest():
    r = screen({"a": good, "b": lambda: good().astype("uint64"), "c": good})
    assert r.outliers == ("b",)


def test_fewer_than_two_executors_raises():
    with pytest.raises(VerificationError, match="at least 2"):
        screen({"a": good})


def test_real_kernel_on_three_cpu_executors_is_healthy():
    r = screen_kernel(collatz, ("cpu", "cpu", "cpu"), 32, limit=100)
    assert r.healthy and [x.name for x in r.results] == ["cpu#0", "cpu#1", "cpu#2"]


@needs_metal
def test_real_kernel_cpu_cpu_metal_is_healthy_because_the_integer_kernel_is_bit_exact():
    r = screen_kernel(collatz, ("cpu", "cpu", "metal"), 64, limit=300)
    assert r.healthy and r.majority is not None


def test_cli_screen_healthy(capsys):
    from spatial.cli import main
    assert main(["screen", "--devices", "cpu,cpu,cpu", "--n", "16", "--params", '{"limit":100}']) == 0
    assert "HEALTHY: all 3 executors agree" in capsys.readouterr().out


def test_cli_screen_with_a_simulated_fault_names_the_executor_and_exits_nonzero(capsys):
    from spatial.cli import main
    assert main(["screen", "--devices", "cpu,cpu,cpu", "--n", "16", "--params", '{"limit":100}', "--simulate-fault", "1"]) == 1
    out = capsys.readouterr().out
    assert "SIMULATED fault" in out and "outlier" in out and "UNHEALTHY" in out and "cpu#1" in out

"""Redundant-execution verification: trust a result only if an independent second execution agrees."""
import numpy as np
import pytest

from spatial.fabric import metal
from spatial.kernel.library import batch_score, collatz, mandelbrot
from spatial.verify import VerificationError, consensus, verify_kernel

needs_metal = pytest.mark.skipif(not metal.available(), reason="no Metal")


def test_two_identical_results_agree_exact():
    a = np.array([[1, 2], [3, 4]], dtype="uint32")
    b = a.copy()
    c = consensus([a, b], exact=True)
    assert c.agreed and c.max_abs_diff == 0.0 and c.n_results == 2


def test_two_differing_results_disagree_exact():
    a = np.array([[1, 2], [3, 4]], dtype="uint32")
    b = np.array([[1, 2], [3, 99]], dtype="uint32")
    c = consensus([a, b], exact=True)
    assert not c.agreed and c.max_abs_diff == 95.0
    assert "differ" in c.reason


def test_float_results_within_tolerance_agree():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0, 3.04])
    c = consensus([a, b], tolerance=0.05)
    assert c.agreed and c.max_abs_diff == pytest.approx(0.04)


def test_float_results_outside_tolerance_disagree():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0, 3.5])
    c = consensus([a, b], tolerance=0.05)
    assert not c.agreed and "exceeds tolerance" in c.reason


def test_three_results_checked_pairwise_against_the_first():
    a = np.array([1, 2, 3])
    b = np.array([1, 2, 3])
    bad = np.array([1, 2, 4])
    assert consensus([a, b, b], exact=True).agreed
    assert not consensus([a, b, bad], exact=True).agreed


def test_single_result_raises():
    with pytest.raises(VerificationError, match="at least 2"):
        consensus([np.array([1, 2])])


def test_shape_mismatch_raises():
    with pytest.raises(VerificationError, match="shape mismatch"):
        consensus([np.array([1, 2]), np.array([1, 2, 3])])


def test_verify_kernel_cpu_against_itself_agrees_exact():
    c = verify_kernel(collatz, ("cpu", "cpu"), 8, exact=True, limit=100)
    assert c.agreed and c.n_results == 2


@needs_metal
def test_verify_kernel_cpu_vs_metal_integer_kernel_agrees_exact():
    c = verify_kernel(collatz, ("cpu", "metal"), 64, exact=True, limit=300)
    assert c.agreed


@needs_metal
def test_verify_kernel_cpu_vs_metal_float_kernel_agrees_within_tolerance():
    c = verify_kernel(mandelbrot, ("cpu", "metal"), 128, tolerance=50, iters=100)
    assert c.agreed
    c2 = verify_kernel(batch_score, ("cpu", "metal"), 64, tolerance=5, signals=16)
    assert c2.agreed


def test_cli_verify_runs(capsys):
    from spatial.cli import main
    assert main(["verify", "--family", "collatz", "--n", "8", "--devices", "cpu,cpu", "--exact", "--params", '{"limit":100}']) == 0
    out = capsys.readouterr().out
    assert "AGREE" in out


def test_cli_verify_disagree_exits_nonzero(capsys, monkeypatch):
    import spatial.kernel.library as lib
    from spatial.kernel.dsl import Kernel

    calls = {"n": 0}
    real_run = lib.collatz.run

    def fake_run(device, n, **params):
        calls["n"] += 1
        out = real_run(device, n, **params)
        if calls["n"] == 2:
            out = out.copy()
            out[0, 0] += 1
        return out

    monkeypatch.setattr(lib.collatz, "run", fake_run)
    from spatial.cli import main
    assert main(["verify", "--family", "collatz", "--n", "8", "--devices", "cpu,cpu", "--exact", "--params", '{"limit":100}']) == 1
    assert "DISAGREE" in capsys.readouterr().out

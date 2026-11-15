"""v0.7: asymmetric readout error in the SPATIAL Q simulator."""
import numpy as np
import pytest

from spatial.q import compile_kernel, parse, sim


def test_readout_channel_is_exact_and_conserves_probability():
    v = np.array([0.0, 0.0, 0.0, 1.0])                    # |11> on 2 qubits
    out = sim.apply_readout(v, 2, p01=0.0, p10=0.1)
    assert out.sum() == pytest.approx(1.0)
    assert out[3] == pytest.approx(0.81) and out[1] == pytest.approx(0.09) and out[2] == pytest.approx(0.09)
    assert out[0] == pytest.approx(0.01)
    z = sim.apply_readout(np.array([1.0, 0, 0, 0]), 2, p01=0.2, p10=0.5)   # |00>: only p01 matters
    assert z[0] == pytest.approx(0.64) and z.sum() == pytest.approx(1.0)
    assert np.array_equal(sim.apply_readout(v, 2, 0.0, 0.0), v)
    with pytest.raises(ValueError):
        sim.apply_readout(v, 2, 1.5, 0.0)


def test_sampling_with_readout_matches_the_channel_and_is_asymmetric():
    k = parse("quantum k() { qubit q[1]; x q[0]; } main { }").kernels["k"]
    c, _ = compile_kernel(k, [])
    shots = 40000
    counts = sim.sample(c, shots, seed=3, readout=(0.0, 0.07))
    assert counts["0"] / shots == pytest.approx(0.07, abs=0.006)         # |1> decays toward 0 when read
    zero, _ = compile_kernel(parse("quantum z() { qubit q[1]; h q[0]; h q[0]; } main { }").kernels["z"], [], opt=False)
    assert sim.sample(zero, shots, seed=3, readout=(0.0, 0.07)) == {"0": shots}   # |0> is untouched when p01 = 0


def test_trajectory_path_applies_readout_too():
    k = parse("quantum k() { qubit q[1]; x q[0]; } main { }").kernels["k"]
    c, _ = compile_kernel(k, [])
    counts = sim.sample(c, 6000, seed=4, noise=0.0001, readout=(0.0, 0.2))
    assert counts.get("0", 0) / 6000 == pytest.approx(0.2, abs=0.02)

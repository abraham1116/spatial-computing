"""TEST 5 — SPATIAL Q vs existing tools (Qiskit / Qiskit Aer) on the same circuits.

A. Correctness: state fidelity between the SPATIAL Q simulator and Qiskit's Statevector.
B. Speed: sampling time, built-in NumPy simulator vs Aer (C++), growing qubit count.
C. Compiler: front-end + optimiser time and gate reduction.
D. Optimisation loop: dynamic-circuit sampling, per-shot vs branch enumeration.
E. Hybrid program (VQE) vs exact diagonalisation.
All of this is CLASSICAL SIMULATION of quantum circuits: no quantum speed-up is measured.
"""
from __future__ import annotations

import time

import numpy as np
import psutil

from common import ROOT, save, timeit
from spatial.q import compile_kernel, parse, run_source, sim
from spatial.q.backends import get, to_qiskit

SRC = """
quantum layered(n, depth) {
    qubit q[n];
    for d in 0..depth {
        for i in 0..n { ry(0.1 * (i + 1) + 0.37 * d) q[i]; rz(0.2 * (d + 1)) q[i]; }
        for i in 0..n - 1 { cx q[i], q[i + 1]; }
    }
}
main { }
"""


def main():
    from qiskit.quantum_info import Statevector
    prog = parse(SRC)
    aer, sv = get("aer"), get("statevector")
    out = {"scaling": [], "note": "classical simulation only; no QPU was used"}
    for n in (4, 8, 12, 16, 20, 22):
        t0 = time.perf_counter()
        c, info = compile_kernel(prog.kernels["layered"], [n, 4])
        compile_s = time.perf_counter() - t0
        rep = 3 if n <= 16 else 1
        t_sv, _, counts = timeit(lambda: sv.sample(c, 1000, seed=1), rep)
        t_aer, _, counts_aer = timeit(lambda: aer.sample(c, 1000, seed=1), rep)
        row = {"qubits": n, "ops": len(c.ops), "compile_s": compile_s, "statevector_MB": 16 * 2 ** n / 1e6,
               "spatialq_numpy_s": t_sv, "aer_s": t_aer, "ratio_spatialq_over_aer": t_sv / t_aer}
        if n <= 16:
            ref = np.asarray(Statevector(to_qiskit(c, measure_all=False)))
            row["fidelity_vs_qiskit"] = float(abs(np.vdot(ref, sim.run_static(c).vector())) ** 2)
        out["scaling"].append(row)
        print(row)
    avail = psutil.virtual_memory().available
    out["max_qubits_exact_here"] = int(np.floor(np.log2(0.5 * avail / 16)))
    out["ram_available_GB"] = avail / 1e9

    # C. optimiser on the examples
    ex = parse((ROOT / "examples/05_ghz_qft.sq").read_text())
    out["optimizer"] = []
    for n in (4, 8, 12):
        t0 = time.perf_counter()
        c, info = compile_kernel(ex.kernels["qft_roundtrip"], [n])
        out["optimizer"].append({"kernel": f"qft_roundtrip({n})", **info, "compile_s": time.perf_counter() - t0})
    print(out["optimizer"])

    # D. dynamic circuits
    tp = parse((ROOT / "examples/04_teleport.sq").read_text())
    c, _ = compile_kernel(tp.kernels["teleport"], [1.0])
    t_shots, _, _ = timeit(lambda: sim.sample(c, 4000, seed=1, dynamic="shots"), 1)
    t_branch, _, cb = timeit(lambda: sim.sample(c, 4000, seed=1, dynamic="branch"), 5)
    t_aer, _, ca = timeit(lambda: aer.sample(c, 4000, seed=1), 3)
    p1 = sum(v for k, v in cb.items() if k[0] == "1") / 4000
    out["dynamic"] = {"shots": 4000, "per_shot_s": t_shots, "branch_enumeration_s": t_branch, "aer_s": t_aer,
                      "speedup_branch_vs_per_shot": t_shots / t_branch, "p_q2_is_1": p1,
                      "expected": float(np.sin(0.5) ** 2)}
    print(out["dynamic"])

    # E. hybrid VQE
    t0 = time.perf_counter()
    env, rt = run_source((ROOT / "examples/03_vqe_hybrid.sq").read_text(), out=lambda *a: None)
    Z, X, Y, I = sim.FIXED["z"], sim.FIXED["x"], sim.FIXED["y"], np.eye(2)
    H = (-0.4804 * np.kron(I, I) + 0.3435 * np.kron(I, Z) - 0.4347 * np.kron(Z, I) + 0.5716 * np.kron(Z, Z)
         + 0.0910 * np.kron(X, X) + 0.0910 * np.kron(Y, Y))
    exact = float(np.linalg.eigvalsh(H).min())
    out["vqe"] = {"energy": env["e"], "exact": exact, "abs_error": abs(env["e"] - exact),
                  "wall_s": time.perf_counter() - t0,
                  "quantum_evaluations": sum(1 for t in rt.trace if t["op"] == "expect")}
    print(out["vqe"])
    save("spatialq", out)


if __name__ == "__main__":
    main()

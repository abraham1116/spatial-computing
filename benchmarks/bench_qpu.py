"""Real quantum hardware (IBM) versus the SPATIAL Q simulators on the same circuits.

One batched job on the least busy real backend. For each circuit we compare:
  ideal simulation  (exact distribution),
  hardware counts   (what the QPU returned),
  noisy simulation  (depolarising noise p fitted to the hardware by a grid search).
Metric: total variation distance (TVD, 0 = identical, 1 = disjoint).

Reading the result: a single-qubit depolarising probability applied per logical gate is a
crude model of the device (it ignores transpilation, connectivity, readout error and
crosstalk). The fit tells how far one number can explain real noise: it does not validate
the noise model.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

from common import ROOT, save
from spatial.q import compile_kernel, parse, sim
from spatial.q.backends import _ibm_token, to_qiskit

SRC = """
quantum bell() { qubit q[2]; h q[0]; cx q[0], q[1]; }
quantum ghz(n) { qubit q[n]; h q[0]; for i in 0..n - 1 { cx q[i], q[i + 1]; } }
quantum qft_rt(n) {
    qubit q[n];
    for i in 0..n { h q[i]; for j in i + 1..n { cp(pi / pow(2, j - i)) q[j], q[i]; } }
    for k in 0..n { let i = n - 1 - k; for jj in 0..n - 1 - i { let j = n - 1 - jj; cp(-pi / pow(2, j - i)) q[j], q[i]; } h q[i]; }
}
quantum layered(n, depth) {
    qubit q[n];
    for d in 0..depth {
        for i in 0..n { ry(0.1 * (i + 1) + 0.37 * d) q[i]; rz(0.2 * (d + 1)) q[i]; }
        for i in 0..n - 1 { cx q[i], q[i + 1]; }
    }
}
main { }
"""
CASES = [("bell", [], "bell"), ("ghz3", [3], "ghz"), ("ghz5", [5], "ghz"), ("qft_roundtrip3", [3], "qft_rt"),
         ("layered4x2", [4, 2], "layered")]
SHOTS = 1000


def tvd(p: np.ndarray, q: np.ndarray) -> float:
    return 0.5 * float(np.abs(p - q).sum())


def vec(counts: dict, n: int) -> np.ndarray:
    v = np.zeros(1 << n)
    for k, c in counts.items():
        v[int(k, 2)] += c
    return v / v.sum()


FIT_SHOTS = 3000          # trajectories per noise level (noisy simulation is one run per shot)


def main():
    from qiskit import transpile
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
    reuse = os.environ.get("SPATIAL_QPU_JOB")      # re-analyse an existing job instead of paying QPU time again
    prog = parse(SRC)
    circuits = {}
    for name, args, kernel in CASES:
        c, _ = compile_kernel(prog.kernels[kernel], args, opt=False)      # keep every gate: the QPU must do the work
        circuits[name] = c
    svc = QiskitRuntimeService(channel="ibm_quantum_platform", token=_ibm_token())
    backend = svc.least_busy(operational=True, simulator=False, min_num_qubits=5)
    print("backend:", backend.name, "pending:", backend.status().pending_jobs, flush=True)
    qcs = {n: transpile(to_qiskit(c), backend, optimization_level=1) for n, c in circuits.items()}
    t0 = time.time()
    if reuse:
        job = svc.job(reuse)
        backend = job.backend()
    else:
        job = SamplerV2(mode=backend).run(list(qcs.values()), shots=SHOTS)
    print("job:", job.job_id(), backend.name, flush=True)
    res = job.result()
    wall = time.time() - t0
    try:
        usage = job.usage() if callable(getattr(job, "usage", None)) else None
    except Exception:
        usage = None
    pgrid = [0.0, 0.005, 0.01, 0.02]
    ro_grid = [(a, b) for a in (0.0, 0.005, 0.01, 0.02, 0.03) for b in np.round(np.arange(0.0, 0.151, 0.01), 3)]
    cache: dict = {}

    def noisy(name, p):
        if (name, p) not in cache:
            c = circuits[name]
            cache[(name, p)] = vec(sim.sample(c, FIT_SHOTS, seed=1, noise=float(p)), c.n_qubits)
        return cache[(name, p)]

    def model(name, p, ro):
        return sim.apply_readout(noisy(name, p), circuits[name].n_qubits, ro[0], float(ro[1]))

    hwv = {nm: vec(res[i].data.c.get_counts(), circuits[nm].n_qubits) for i, (nm, _, _) in enumerate(CASES)}
    rows = []
    for (name, c), r in zip(circuits.items(), res):
        n, hw = c.n_qubits, hwv[name]
        ideal = np.abs(sim.run_static(c).vector()) ** 2
        rng = np.random.default_rng(7)               # distance a PERFECT device would show with this many shots
        floor = float(np.mean([tvd(ideal, rng.multinomial(SHOTS, ideal / ideal.sum()) / SHOTS) for _ in range(300)]))
        dep = min(((tvd(noisy(name, p), hw), p) for p in pgrid))
        ro_only = min(((tvd(model(name, 0.0, ro), hw), ro) for ro in ro_grid))
        both = min(((tvd(model(name, p, ro), hw), p, ro) for p in pgrid for ro in ro_grid))
        ty = sorted(({format(i, f'0{n}b'): float(v) for i, v in enumerate(hw)}).items(), key=lambda kv: -kv[1])[:3]
        rows.append({"circuit": name, "qubits": n, "gates_logical": len(c.ops),
                     "gates_transpiled": int(sum(qcs[name].count_ops().values())),
                     "two_qubit_transpiled": int(sum(v for k, v in qcs[name].count_ops().items() if k in ("cx", "cz", "ecr", "swap"))),
                     "sampling_floor_tvd": floor, "tvd_ideal_vs_hardware": tvd(ideal, hw),
                     "depolarising_only": {"p": dep[1], "tvd": dep[0]},
                     "readout_only": {"p01": ro_only[1][0], "p10": float(ro_only[1][1]), "tvd": ro_only[0]},
                     "both": {"p": both[1], "p01": both[2][0], "p10": float(both[2][1]), "tvd": both[0]},
                     "hardware_top3": ty})
        print(name, f"floor {floor:.3f} ideal {tvd(ideal, hw):.3f} dep {dep[0]:.3f} readout {ro_only[0]:.3f} both {both[0]:.3f}", flush=True)
    # one set of parameters for ALL circuits (is the model predictive, or just flexible?)
    shared = min(((sum(tvd(model(nm, p, ro), hwv[nm]) for nm, _, _ in CASES), p, ro) for p in pgrid for ro in ro_grid))
    shared_tvd = {nm: tvd(model(nm, shared[1], shared[2]), hwv[nm]) for nm, _, _ in CASES}
    shared_p = {"p": shared[1], "p01": shared[2][0], "p10": float(shared[2][1])}
    out = {"backend": backend.name, "job_id": job.job_id(), "shots_per_circuit": SHOTS, "wall_s": wall,
           "usage": str(usage) if usage is not None else None, "rows": rows, "shared_parameters": shared_p, "tvd_with_shared_parameters": shared_tvd, "fit_shots": FIT_SHOTS,
           "note": "model = depolarising p per logical gate and qubit + independent asymmetric readout error (p01, p10); still a crude stand-in for the device"}
    save("qpu_vs_sim", out)


if __name__ == "__main__":
    main()

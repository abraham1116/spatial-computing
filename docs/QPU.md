# Real quantum hardware versus the simulator

Measured on 2026-11-15 on IBM Quantum (open plan), backend `ibm_marrakesh` (156 qubits), job `dbsu35fasvbs73b93hr0`, 1000 shots per circuit, circuits transpiled at optimization level 1. Reproduce the analysis without paying QPU time again:

```bash
SPATIAL_QPU_JOB=dbsu35fasvbs73b93hr0 python benchmarks/bench_qpu.py   # needs the IBM token
```

Raw data: `benchmarks/results/qpu_vs_sim.json` (and `qpu_bell.json` for the first Bell run).

## Metric

Total variation distance (TVD) between the outcome distributions: 0 means identical, 1 means disjoint. A perfect device would still show a small distance with 1000 shots; that is the **sampling floor**.

## Result

| Circuit | Qubits | Gates after transpilation (2-qubit) | Sampling floor | Ideal vs hardware | Depolarising only | Readout error only | Both |
|---|---|---|---|---|---|---|---|
| bell | 2 | 12 (1) | 0.013 | 0.088 | 0.069 | 0.042 | 0.037 |
| ghz3 | 3 | 20 (2) | 0.013 | 0.107 | 0.101 | 0.059 | 0.058 |
| ghz5 | 5 | 36 (4) | 0.013 | 0.155 | 0.141 | 0.095 | 0.095 |
| qft_roundtrip3 | 3 | 103 (18) | 0.000 | 0.058 | 0.022 | 0.017 | 0.017 |
| layered4x2 | 4 | 63 (6) | 0.032 | 0.073 | 0.058 | 0.054 | 0.054 |

One shared parameter set for all five circuits (depolarising p = 0.005, P(read 0 | was 1) = 0.07, P(read 1 | was 0) = 0) gives distances 0.048, 0.058, 0.099, 0.020 and 0.061: it improves every circuit over the ideal simulation.

## Reading

- **The hardware error is real and large**: 3 to 12 times the sampling floor on Bell and GHZ.
- **It is asymmetric.** On Bell, `00` came out at 49.8 % and `11` at 41.4 %; on GHZ-3, `000` 49.9 % and `111` 39.4 %. A symmetric depolarising error cannot produce that; a bias toward reading 0 (the excited state relaxes, and is misread) does. Adding asymmetric readout error roughly halves the gap, and one parameter set transfers across circuits.
- **Error grows with circuit size**: GHZ-5 (4 two-qubit gates) is the worst of the three shallow circuits.
- **A deep circuit can still work**: the QFT round trip became 103 gates (18 two-qubit) after transpilation and still returned `000` 94.2 % of the time.

## Limits of this result

- One backend, one day, one job, five small circuits. Device noise changes between calibrations.
- The fitted "readout" parameter is **effective**: it also absorbs relaxation during the circuit. It is not the device's published readout error.
- Part of the residual (GHZ-5: 0.095 against a floor of 0.013) is not modelled: correlated errors, crosstalk, gate errors that depend on the qubit pair.
- Parameters are fitted on the same data they are scored on (a grid of 96 settings, 3 parameters, 5 circuits). The shared fit is the fairer number, and it is still in-sample.
- No quantum advantage is shown or claimed.

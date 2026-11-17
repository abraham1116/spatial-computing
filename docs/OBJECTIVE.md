# One objective for the whole infrastructure

Every engine used to answer its own question: Compute asked "which strategy is fastest", Memory "does it fit", Runtime "which route runs", the AI engine "recompute or restore", the Fleet "which node". They now answer **one** question:

> **Get the job done correctly at the lowest cost in dollars, within the constraints you state, and prove it.**

*Correctly*: variants must agree on the result. *Constraints*: deadline, RAM, isolation, hardware allowed. *Prove it*: every executed plan records the estimate next to what really happened, and the next estimates are corrected by that history.

## How it is built

```
            Job  +  Objective  +  Prices
                       |
                   [ Planner ]   one ranking function, one cost formula, one ledger
                       |
   +-----------+-------+-------+-----------+-----------+
   compute     fleet   memory   runtime     kv (AI)
   provider    provider provider provider    provider
   mandel      each    in RAM   native      recompute
   collatz     alive   vs       WASM        vs restore
   batch_score node    tiered   micro-VM    from tier
   + verticals at its  over     Wine
               own     SSD
               price
```

| Engine | What its provider contributes |
|---|---|
| Compute (incl. portable kernels) | Numerical and batch-scoring families. Each variant is probed on reduced problems (best of several runs, two sizes, affine fit: fixed cost + cost per unit of work), checked against the other variants, then extrapolated. |
| Fleet | The same job on each live node, priced at the node's own rate (`--usd-per-hour`), executed through the hub. A node with no price is rejected, not guessed. |
| Tiered memory | A dataset kept in RAM or tiered over SSD, with tier latencies measured on this machine and a locality model for the hit ratio. Validated by running the real store at reduced scale. |
| Runtime | Every route for a binary with its isolation and measured overhead. |
| AI | A cached prefix: recompute, or keep and restore. Validated by checking the restored cache gives exactly the recomputed logits. |

## Use

```bash
spatial optimize compute --family pk_batch_score --params '{"n":512,"signals":16}' --execute
spatial optimize dataset --gib 24 --accesses 200000 --max-ram-gib 2
spatial optimize kv --prefix-tokens 2000 --reuse 0.8 --execute
spatial optimize binary --file app.elf --isolated 64 50
```

```python
from spatial.unified import Planner, Job, Objective, Prices
pl = Planner(prices=Prices(local_usd_per_hour=0.134))
plan, run = pl.run(Job.compute("mandel", n=800, iters=300), Objective(deadline_s=5))
print(plan.explain(), run.time_error_pct)
```

## Is the decision good? (benchmarks/bench_unified.py)
Each case: the planner chooses from its estimates, then **every feasible option is run for real**. On one machine with one price per hour, cheapest = fastest.

| Version of the estimator | Cases | Planner picked the truly fastest | Mean regret | Median estimate error |
|---|---|---|---|---|
| Single probe at 1/8 size | 13 | 10 (77 %) | 1.10x | 28 % |
| Two sizes, affine fit | 13 | 10 (77 %) | 1.12x | 16 % |
| + best-of-several probes | 13 | 12 (92 %) | 1.007x | 7 % |
| Same, on 12 cases never used while tuning | 12 | 12 (100 %) | 1.00x | 5 % |

How it improved: the first versions mis-ranked the multi-core variant on mid-size jobs because microsecond probes were dominated by thread start-up noise; taking the best of several runs fixed it. Earlier results are kept in `benchmarks/results/unified_v1_single_probe.json` and `unified_v2_affine_single_run.json`.

## Limits
- One machine, 25 cases, one family of numerical jobs. These cases predate the removal of the quantum and scientific-simulation engines (see CHANGELOG) and have not been rerun against the current, smaller set of providers.
- Estimates come from probes and measured constants on **this** machine; they are not portable to another one without re-probing (the planner re-probes at each plan).
- Calibration is a median of past actual/estimate ratios, not a learned model.
- Dollar costs use the prices you give. The default local price (0.134 $/h) is an assumption. Fleet nodes need their own price.
- Fleet execution assumes a node runs at this machine's speed, slowed by the node's load: an assumption, not a measurement.
- The AI engine is a toy NumPy model; its restore-versus-recompute numbers say nothing about real LLMs or GPUs.
- Not tested: more than one real machine, GPUs, real money.

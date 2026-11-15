"""TEST — the virtual interconnect: measured all-reduce versus the alpha-beta model, and whether the
model picks the really fastest algorithm. N ranks are N OS processes on this machine talking over the
encrypted SWP/2 transport on loopback, so the numbers describe the SOFTWARE LAYER, not a network.
NVLink 5 reference (vendor figure): 900 GB/s per GPU per direction."""
from __future__ import annotations

import json

from common import save
from spatial.interconnect import launch, tasks
from spatial.interconnect.model import choose, choose_calibrated, fit_algo

NVLINK5_BYTES_PER_S = 900e9
SIZES = [256, 4096, 1 << 16, 1 << 18, 1 << 20, 1 << 22]          # float32 elements: 1 KiB .. 16 MiB


def main():
    out = {"nvlink5_per_direction_Bps": NVLINK5_BYTES_PER_S, "runs": []}
    for n in (4, 8):
        algos = ("ring", "halving_doubling", "tree")
        res = launch(n, tasks.bench_all, SIZES, algos, 5, timeout_s=900)[0]
        right = 0
        for row in res["rows"]:
            row["model_choice"], _ = choose(n, row["bytes"], res["alpha_s"], res["beta_Bps"])
            row["measured_best"] = min(row["measured_s"], key=row["measured_s"].get)
            row["choice_regret"] = row["measured_s"][row["model_choice"]] / row["measured_s"][row["measured_best"]]
            row["bus_bandwidth_Bps"] = {a: 2 * (n - 1) / n * row["bytes"] / t for a, t in row["measured_s"].items()}
            right += row["model_choice"] == row["measured_best"]
            print(f"N={n} {row['bytes']:>9} B  model {row['model_choice']:<17} best {row['measured_best']:<17} regret {row['choice_regret']:.2f}x  "
                  f"best bus bw {max(row['bus_bandwidth_Bps'].values()) / 1e6:8.1f} MB/s", flush=True)
        res.update(ranks=n, model_choice_correct=right, cases=len(res["rows"]),
                   mean_regret=sum(r["choice_regret"] for r in res["rows"]) / len(res["rows"]))
        print(f"N={n}: alpha {res['alpha_s'] * 1e6:.0f} us, beta {res['beta_Bps'] / 1e6:.0f} MB/s, model right {right}/{len(res['rows'])}")
        out["runs"].append(res)
    # Calibrated per algorithm on N=4 only, then judged on N=8 (a rank count it never saw), and
    # leave-one-size-out on N=8 itself: held-out, not in-sample.
    algos = ("ring", "halving_doubling", "tree")
    r4, r8 = out["runs"][0]["rows"], out["runs"][1]["rows"]
    fits4 = {a: fit_algo(a, 4, [(r["bytes"], r["measured_s"][a]) for r in r4]) for a in algos}
    held = {"fit_on": "N=4", "judged_on": "N=8", "rows": []}
    for r in r8:
        pick, _ = choose_calibrated(8, r["bytes"], fits4)
        held["rows"].append({"bytes": r["bytes"], "pick": pick, "best": r["measured_best"],
                             "regret": r["measured_s"][pick] / r["measured_s"][r["measured_best"]]})
    held["correct"] = sum(x["pick"] == x["best"] for x in held["rows"])
    held["mean_regret"] = sum(x["regret"] for x in held["rows"]) / len(held["rows"])
    loso = []
    for k, r in enumerate(r8):
        fits = {a: fit_algo(a, 8, [(q["bytes"], q["measured_s"][a]) for j, q in enumerate(r8) if j != k]) for a in algos}
        pick, _ = choose_calibrated(8, r["bytes"], fits)
        loso.append({"bytes": r["bytes"], "pick": pick, "best": r["measured_best"],
                     "regret": r["measured_s"][pick] / r["measured_s"][r["measured_best"]]})
    out["calibrated_heldout_other_N"] = held
    out["calibrated_leave_one_size_out_N8"] = {"rows": loso, "correct": sum(x["pick"] == x["best"] for x in loso),
                                               "mean_regret": sum(x["regret"] for x in loso) / len(loso)}
    for name, h in (("calibrated N=4 -> N=8", held), ("calibrated leave-one-size-out N=8", out["calibrated_leave_one_size_out_N8"])):
        print(f"{name}: right {h['correct']}/{len(h['rows'])}, mean regret {h['mean_regret']:.2f}x", flush=True)
    peak = max(max(r["bus_bandwidth_Bps"].values()) for run in out["runs"] for r in run["rows"])
    out["peak_bus_bandwidth_Bps"] = peak
    out["ratio_to_nvlink5"] = NVLINK5_BYTES_PER_S / peak
    save("interconnect", out)
    print(f"peak bus bandwidth {peak / 1e6:.0f} MB/s: NVLink 5 is {out['ratio_to_nvlink5']:.0f}x faster per direction")


if __name__ == "__main__":
    main()

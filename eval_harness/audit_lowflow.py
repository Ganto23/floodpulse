"""Audit: booster behaviour by flow regime (dry/low/normal/high/surge) on 2024, from FP_DUMP arrays."""
import json, glob
import numpy as np, pandas as pd
out = {}
for p in sorted(glob.glob("results/audit/*_2024_*.npz")):
    g, var = p.split("/")[-1].replace(".npz", "").split("_2024_")
    d = np.load(p)
    yt, v = d["yt"], d["valid"]
    q = json.load(open(f"results/audit/{g}.json"))
    p95, thr = q["p95"], q["p99_threshold"]
    lev = pd.Series(yt[v])
    bins = {"below P25": lev < lev.quantile(.25), "P25-P75": (lev >= lev.quantile(.25)) & (lev < lev.quantile(.75)),
            "P75-P95": (lev >= lev.quantile(.75)) & (yt[v] < p95), "surge >P95": pd.Series(yt[v] >= p95)}
    res = {}
    for m in ("timesfm", "booster_nophys", "booster"):
        e = (d[m] - yt)[v]
        res[m] = {k: {"bias_m": float(e[b.to_numpy()].mean()), "mae_m": float(np.abs(e[b.to_numpy()]).mean()), "n": int(b.sum())} for k, b in bins.items()}
        # spurious threshold forecasts while the river is in its lower half
        low = (yt[v] < lev.median())
        res[m]["pred_above_P99_while_actual_below_median"] = int(((d[m][v] >= thr) & low).sum())
        res[m]["pred_above_P95_while_actual_below_median"] = int(((d[m][v] >= p95) & low).sum())
    out[f"{g}/{var}"] = res
    print(f"\n== {g} · {var}   (bias = mean pred − actual, m)")
    for m, r in res.items():
        print(f"   {m:15s} " + " | ".join(f"{k}: {r[k]['bias_m']:+.3f}" for k in bins) +
              f" | false >P95 in lower half: {r['pred_above_P95_while_actual_below_median']}, >P99: {r['pred_above_P99_while_actual_below_median']}")
json.dump(out, open("results/audit/lowflow.json", "w"), indent=1)

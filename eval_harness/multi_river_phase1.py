"""
Phase 1: does the original FloodPulse result (real issued rain forecasts cut 6-24 h river-level
forecast error 37-48%) generalise across gauges? Identical protocol to check_correlation.py:
2023-2024 hourly, DEV = first 80%, TEST = last 20% (Aug-Dec 2024), anomaly view, AR(24) vs
AR(24)+weather, real Open-Meteo Previous-Runs forecasts used in BOTH fit and score.
"""
import json, sys
import numpy as np, pandas as pd
from check_correlation import analyse
from multi_river_fetch import STATIONS, OUT

EXCLUDE = {"greta_low_briery": "no level data after 2020"}
rows, full = [], {}
for slug in STATIONS:
    if slug in EXCLUDE:
        rows.append({"gauge": slug, "excluded": EXCLUDE[slug]}); continue
    df = pd.read_csv(f"data/flood_{slug}.csv", index_col="time", parse_dates=True)
    cov = df["y"].notna().mean()
    if cov < 0.6:
        rows.append({"gauge": slug, "excluded": f"y coverage {cov:.0%}"}); continue
    res = analyse(f"flood_{slug}")
    full[slug] = res
    v = res["views"]["anomaly"]
    best = max(v["lags"].items(), key=lambda kv: abs(kv[1]["best_pearson"]))
    row = {"gauge": slug, "coverage": round(cov, 3),
           "best_feature": best[0], "best_r": round(best[1]["best_pearson"], 3), "best_lag": best[1]["best_lag"],
           "p_eff": best[1]["p_eff"]}
    for h in (6, 12, 24):
        f, o, p = v["incremental_forecast"][h], v["incremental_oracle"][h], v["incremental"][h]
        row[f"real_fc_{h}h"] = f["mse_reduction"]; row[f"oracle_{h}h"] = o["mse_reduction"]
        row[f"past_{h}h"] = p["mse_reduction"]; row[f"r2_ar_{h}h"] = f["r2_test_ar"]; row[f"r2_arx_{h}h"] = f["r2_test_arx"]
    rows.append(row)
(OUT / "phase1.json").write_text(json.dumps({"rows": rows}, indent=1, default=str))
pct = lambda x: f"{-x:+.0%}" if x is not None and not (isinstance(x, float) and np.isnan(x)) else "  n/a"
print(f"{'gauge':22s}{'best X (r, lag)':>34s} | real issued fc: 6h   12h   24h | bound 24h | past-only 24h | R² 24h AR→ARX")
for r in rows:
    if "excluded" in r:
        print(f"{r['gauge']:22s}  EXCLUDED: {r['excluded']}"); continue
    bx = "%s (%+.2f, %dh)" % (r["best_feature"], r["best_r"], r["best_lag"])
    print(f"{r['gauge']:22s}{bx:>34s} |            {pct(r['real_fc_6h']):>5s} {pct(r['real_fc_12h']):>5s} {pct(r['real_fc_24h']):>5s}"
          f" |  {pct(r['oracle_24h']):>6s}  |    {pct(r['past_24h']):>6s}    | {r['r2_ar_24h']:.2f}->{r['r2_arx_24h']:.2f}")
ok = [r for r in rows if "excluded" not in r]
for h in (6, 12, 24):
    v = np.array([r[f"real_fc_{h}h"] for r in ok], float)
    print(f"real-forecast error reduction @{h}h: median {np.median(v):.1%}  mean {np.mean(v):.1%}  min {v.min():.1%}  max {v.max():.1%}  (n={len(v)})")

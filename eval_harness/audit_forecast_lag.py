"""
Audit: is the Phase-1 "real issued forecast" result inflated by publication latency?

_previous_day1 = value predicted 24 h before valid time (Open-Meteo docs). The docs give no
publication latency; global runs typically appear a few hours after initialisation, so for
horizons h > ~20 h a day1 forecast may not yet be public at the decision time. Re-run Phase 1 with
_previous_day2 (issued 48 h before valid time, always public by then): a strictly conservative
lower bound for the same test.
"""
import json
import numpy as np, pandas as pd
from fetch_data import DATA
from multi_river_fetch import STATIONS, open_meteo
from check_correlation import analyse

rows = []
for slug, (river, label, _, lat, lon) in STATIONS.items():
    src = DATA / f"flood_{slug}.csv"
    df = pd.read_csv(src, index_col="time", parse_dates=True)
    if slug == "greta_low_briery" or df["y"].notna().mean() < 0.6:
        continue
    pts = [(lat, lon)] + [(lat + dy, lon + dx) for dy, dx in ((0.08, 0), (-0.08, 0), (0, 0.12), (0, -0.12))]
    fc2 = open_meteo("https://previous-runs-api.open-meteo.com/v1/forecast", pts, ["precipitation", "temperature_2m"], "_previous_day2")
    fc2.columns = [f"fc_{c.replace('_previous_day2', '')}" for c in fc2.columns]
    d2 = df.drop(columns=["fc_precipitation", "fc_temperature_2m"]).join(fc2, how="left")
    d2.to_csv(DATA / f"flood_{slug}_d2.csv")
    r1 = json.loads((DATA / "rivers" / "phase1.json").read_text())["rows"]
    base = next(r for r in r1 if r["gauge"] == slug)
    res = analyse(f"flood_{slug}_d2")["views"]["anomaly"]["incremental_forecast"]
    row = {"gauge": slug}
    for h in (6, 12, 24):
        row[f"d1_{h}"] = base[f"real_fc_{h}h"]; row[f"d2_{h}"] = res[h]["mse_reduction"]
    rows.append(row)
    print(f"{slug:22s} " + "  ".join(f"{h}h: day1 −{row[f'd1_{h}']:.0%} → day2 −{row[f'd2_{h}']:.0%}" for h in (6, 12, 24)), flush=True)
for h in (6, 12, 24):
    print(f"median {h}h: day1 −{np.median([r[f'd1_{h}'] for r in rows]):.0%}  day2 −{np.median([r[f'd2_{h}'] for r in rows]):.0%}")
(DATA / "rivers" / "audit_forecast_lag.json").write_text(json.dumps(rows, indent=1))

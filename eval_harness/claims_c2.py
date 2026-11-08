"""C2 redone event-by-event.
C2a  final rising limb of each peak >= TRAIN P95: walk back from the peak while the river keeps rising
     (tolerating dips < 2% of spread); report its length and the time from 50% of that rise to the peak.
C2b  rain events (>=10 mm in 24 h, after >=24 h with <2 mm). response = (peak in 36 h after event start
     - level at start) / event rain. Does the PREVIOUS event's response predict this one better than
     soil moisture (SSI) or 72 h antecedent rain? Spearman, per gauge.
"""
import json
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr
R = Path(__file__).parent
G = [f.stem for f in sorted((R / "results/floodpulse").glob("*.json")) if "2024" in json.load(open(f))["sets"]]
res = {}
for g in G:
    df = pd.read_csv(R / f"data/rivers/{g}.csv", parse_dates=["time"])
    y = df.y.interpolate(limit=3).values; rain = df.ea_rain.fillna(df.precipitation).fillna(0).values
    tr = (df.time < pd.Timestamp("2024-01-01", tz="UTC")).values
    p50, p95 = np.nanpercentile(y[tr], [50, 95]); s = p95 - p50; tol = 0.02 * s
    ssi = pd.Series(df.soil_moisture_7_to_28cm.values).rank(pct=True).values
    # C2a
    idx = np.where((y[1:-1] >= y[:-2]) & (y[1:-1] > y[2:]) & (y[1:-1] >= p95))[0] + 1
    keep = []
    for i in idx[np.argsort(-y[idx])]:
        if all(abs(i - k) > 48 for k in keep): keep.append(i)
    L, L50 = [], []
    for p in keep:
        t = p; lo = y[p]
        while t > 0 and not np.isnan(y[t - 1]) and y[t - 1] <= y[t] + tol and p - t < 240:
            t -= 1; lo = min(lo, y[t])
        rise = y[p] - y[t]; L.append(p - t)
        L50.append(p - (t + int(np.argmax(y[t:p + 1] >= y[t] + 0.5 * rise))))
    # C2b
    n = len(y); ev = []; i = 24
    c = np.concatenate([[0], np.cumsum(rain)])
    while i < n - 37:
        if c[i] - c[i - 24] < 2 and c[i + 24] - c[i] >= 10 and not np.isnan(y[i]):
            seg = y[i:i + 37]
            if not np.isnan(seg).all():
                ev.append(dict(i=i, rain=c[i + 24] - c[i], resp=(np.nanmax(seg) - y[i]) / (c[i + 24] - c[i]),
                               ssi=ssi[i], ante72=c[i] - c[max(0, i - 72)]))
            i += 36
        else: i += 1
    e = pd.DataFrame(ev)
    e["prev_resp"] = e.resp.shift(1); e["gap_h"] = e.i.diff()
    e = e[(e.gap_h <= 24 * 14)].dropna()    # previous event within 2 weeks
    rho = {k: round(float(spearmanr(e[k], e.resp)[0]), 2) for k in ("prev_resp", "ssi", "ante72")}
    res[g] = dict(C2a=dict(peaks=len(L), median_final_rise_h=float(np.median(L)), pct_le6h=round(float(np.mean(np.array(L) <= 6)), 2),
                           median_last_half_h=float(np.median(L50))), C2b=dict(n=len(e), rho=rho))
    print(g, res[g])
pd.Series(res).to_json(R / "results/urban/claims_c2.json", indent=1)
A = [res[g]["C2a"] for g in G]
print("\nC2a pooled peaks", sum(a["peaks"] for a in A), "| median final rise (median over gauges)", np.median([a["median_final_rise_h"] for a in A]),
      "| share <=6h", round(sum(a["pct_le6h"] * a["peaks"] for a in A) / sum(a["peaks"] for a in A), 2),
      "| median last-half", np.median([a["median_last_half_h"] for a in A]))
for k in ("prev_resp", "ssi", "ante72"):
    v = [res[g]["C2b"]["rho"][k] for g in G]; print(f"C2b rho {k:10} median {np.median(v):+.2f}  wins(>0.2) {sum(x > 0.2 for x in v)}/{len(v)}  {v}")
print("events per gauge", [res[g]["C2b"]["n"] for g in G])

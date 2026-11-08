"""Tests of four claims about the value of a short (<=6 h) FloodPulse window. Real data, no refitting.

C2a  rising limbs of big events (peak >= TRAIN P95) last <= 6 h?            full 2019-2024 record
C2b  does the river's recent response to rain predict how it responds to the NEXT rain
     better than the ERA5 soil-moisture index (SSI) or simple antecedent rain?  2019-2024, Spearman
C3   'surprise' rises (2024 deployed forecast flat, river rises sharply): how often, was the rain recorded
     by gauges / forecast, how much warning does detecting the rise give, does the model correct after?
C4   forecast skill on rising vs falling (recession) limbs                       2024 deployed
Output: results/urban/claims.json
"""
import json
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr

R = Path(__file__).parent
G = [f.stem for f in sorted((R / "results/floodpulse").glob("*.json"))
     if "2024" in json.load(open(f))["sets"]]
TRAIN_END = "2024-01-01"
out = {}

def peaks(y, thr, sep=48):
    idx = np.where((y[1:-1] >= y[:-2]) & (y[1:-1] > y[2:]) & (y[1:-1] >= thr))[0] + 1
    keep = []
    for i in idx[np.argsort(-y[idx])]:
        if all(abs(i - k) > sep for k in keep): keep.append(i)
    return sorted(keep)

for g in G:
    df = pd.read_csv(R / f"data/rivers/{g}.csv", parse_dates=["time"])
    y = df.y.interpolate(limit=3).values
    rain = df.ea_rain.fillna(df.precipitation).fillna(0).values
    tr = (df.time < pd.Timestamp(TRAIN_END, tz="UTC")).values
    p50, p95 = np.nanpercentile(y[tr], 50), np.nanpercentile(y[tr], 95); s = p95 - p50
    sm = df.soil_moisture_7_to_28cm.values
    ssi = pd.Series(sm).rank(pct=True).values  # percentile of soil moisture (whole record; descriptive only)
    o = {}

    # C2a rising-limb duration
    dur = []
    for p in peaks(y, p95):
        w = y[max(0, p - 96):p + 1]
        if np.isnan(w).any(): continue
        trough = int(np.argmin(w)); rise = w[-1] - w[trough]
        # start = first hour after the trough where the river has risen 10% of the total rise
        st = trough + int(np.argmax(w[trough:] >= w[trough] + 0.1 * rise))
        dur.append(len(w) - 1 - st)
    dur = np.array(dur)
    o["C2a"] = dict(events=len(dur), median_rise_h=float(np.median(dur)), pct_le6h=float((dur <= 6).mean()))

    # C2b: gain = rise over next 24 h per mm of next-24 h rain, for origins with >=10 mm coming
    n = len(y); t = np.arange(96, n - 25, 6)
    fut_r = np.array([rain[i + 1:i + 25].sum() for i in t])
    fut_rise = np.array([np.nanmax(y[i + 1:i + 25]) - y[i] for i in t])
    past_r24 = np.array([rain[i - 23:i + 1].sum() for i in t])
    past_rise = np.array([y[i] - np.nanmin(y[i - 24:i + 1]) for i in t])
    past_r72 = np.array([rain[i - 71:i + 1].sum() for i in t])
    m = (fut_r >= 10) & (past_r24 >= 5) & ~np.isnan(fut_rise) & ~np.isnan(past_rise) & ~np.isnan(ssi[t])
    gain = fut_rise[m] / fut_r[m]
    cands = {"recent_response (rise per mm, last 24h)": past_rise[m] / past_r24[m],
             "soil_moisture_index (ERA5 SSI)": ssi[t][m], "antecedent_rain_72h": past_r72[m],
             "level_now": y[t][m]}
    o["C2b"] = dict(n=int(m.sum()), rho={k: round(float(spearmanr(v, gain)[0]), 3) for k, v in cands.items()})

    # C3/C4 on 2024 deployed forecasts
    z = np.load(R / f"results/dashboard/{g}_2024_deployed.npz")
    oo, hh, yt, v = z["o"], z["h"], z["yt"], z["valid"].astype(bool)
    origins = np.unique(oo); H = 24
    def mat(key):
        M = np.full((len(origins), H), np.nan); M[np.searchsorted(origins, oo) , hh - 1] = np.where(v, z[key], np.nan); return M
    A, B, T = mat("yt"), mat("booster"), mat("timesfm")
    y0 = y[origins]
    fc_rise6 = np.nanmax(B[:, :6], 1) - y0; act_rise6 = np.nanmax(A[:, :6], 1) - y0
    surprise = (fc_rise6 < 0.1 * s) & (act_rise6 > 0.5 * s)
    ev = []
    for i in np.where(surprise)[0]:
        if ev and i - ev[-1] < 24: continue
        ev.append(i)
    fc_r = df.fc_precipitation.fillna(0).values
    det = []
    for i in ev:
        oi = origins[i]
        obs6 = rain[oi + 1:oi + 7].sum(); fc6 = fc_r[oi + 1:oi + 7].sum()
        seg = y[oi:oi + 49]; pk = int(np.nanargmax(seg))
        d_idx = int(np.argmax(seg >= seg[0] + 0.1 * s))           # first hour rise is detectable
        j = np.searchsorted(origins, oi + d_idx)                   # forecast issued at detection
        e_before = abs(B[i, 5] - A[i, 5]) / s
        e_after = abs(B[j, 5] - A[j, 5]) / s if j < len(origins) and origins[j] == oi + d_idx else np.nan
        det.append(dict(time=str(df.time[oi]), obs_rain6=round(float(obs6), 1), fc_rain6=round(float(fc6), 1),
                        hours_detect_to_peak=pk - d_idx, err6_before=round(float(e_before), 2),
                        err6_after_detect=round(float(e_after), 2)))
    o["C3"] = dict(surprises=len(det), events=det)

    dy3 = y0 - y[origins - 3]
    limb = np.where(dy3 > 0.05 * s, "rising", np.where(dy3 < -0.05 * s, "falling", "steady"))
    c4 = {}
    for L in ("rising", "falling", "steady"):
        k = limb == L
        c4[L] = dict(share=round(float(k.mean()), 3), **{f"{nm}_mae{h}_per_s": round(float(np.nanmean(abs(M[k, h - 1] - A[k, h - 1])) / s), 3)
                    for nm, M in (("tfm", T), ("booster", B)) for h in (6, 24)})
    o["C4"] = c4
    out[g] = o
    print(g, o["C2a"], o["C2b"]["n"], o["C2b"]["rho"], "surprises", len(det))

json.dump(out, open(R / "results/urban/claims.json", "w"), indent=1)

print("\n=== C2a rising limb (peaks >= P95) ===")
d = [out[g]["C2a"] for g in G]; print("events", sum(x["events"] for x in d), "median of gauge medians", np.median([x["median_rise_h"] for x in d]),
      "share <=6h (pooled)", round(sum(x["pct_le6h"] * x["events"] for x in d) / sum(x["events"] for x in d), 2))
print("\n=== C2b median Spearman rho with next-rain gain across gauges ===")
for k in out[G[0]]["C2b"]["rho"]: print(f"  {k:42} {np.median([out[g]['C2b']['rho'][k] for g in G]):+.2f}  per gauge {[out[g]['C2b']['rho'][k] for g in G]}")
print("\n=== C3 surprises ===")
allev = [e for g in G for e in out[g]["C3"]["events"]]
print("count", len(allev))
if allev:
    a = pd.DataFrame(allev); print(a.describe().round(2).to_string())
    print("rain gauges recorded >=5mm in next 6h:", (a.obs_rain6 >= 5).mean().round(2), " forecast had >=5mm:", (a.fc_rain6 >= 5).mean().round(2))
print("\n=== C4 limb skill (median over gauges, MAE / spread) ===")
for L in ("rising", "falling", "steady"):
    print(L, {k: round(float(np.median([out[g]["C4"][L][k] for g in G])), 3) for k in out[G[0]]["C4"][L]})

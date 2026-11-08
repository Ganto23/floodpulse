"""
Leave-one-river-out (LORO): does the FloodPulse booster work on a river it has never been trained on?

For each test river R (the 9 gauges with 2024 data):
  pooled booster   trained on the OTHER rivers only (all 10 gauges' TRAIN years minus R), then applied to
                   R's 2024 with rain forecasts as issued ("deployed"). R contributes zero training rows.
  in-river booster same recipe trained on R's own TRAIN years: the reference the dashboard numbers come from.
  timesfm, persistence  zero-shot references.

Same splits/inputs as floodpulse_stress.py: TRAIN = < 2024 minus storm windows ±7 d; booster trained on observed
future rain ("oracle" rows), applied with issued forecasts; quantile loss q=0.6, ×5 weight on top-decile runoff.
To make one model work across rivers of very different size, level features and the target residual are
divided by each river's own TRAIN level spread s = P95 − P50 (and centred on P50). Rain stays in mm.
Variant "pooled+catchment" also gets catchment descriptors (log area, Kirpich Tc, BFIHOST, SAAR).
Origins: TRAIN every 6 h, TEST (2024) every 3 h. TimesFM trajectories are cached in results/loro/.
Output: results/loro/loro.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from floodpulse_stress import BUFFER, CTX, GAUGES, H, RIVERS, STORMS, csum, empirical_lag, tfm, wsum

OUT = Path(__file__).parent / "results" / "loro"
OUT.mkdir(parents=True, exist_ok=True)
CATCH = json.loads((RIVERS / "catchments.json").read_text())
CATCH["cragg_dauber_bridge"]["dem_unreliable"] = True


def build(slug: str) -> dict:
    """Feature rows for one gauge: TRAIN (oracle rain) and 2024 TEST (deployed + past)."""
    df = pd.read_csv(RIVERS / f"{slug}.csv", index_col="time", parse_dates=True).astype(float)
    idx, N = df.index, len(df)
    y_raw = df["y"].to_numpy()
    y = df["y"].interpolate(limit=6, limit_area="inside").to_numpy()
    rain = df["ea_rain"].where(df["ea_rain"].notna(), df["precipitation"]).fillna(0).to_numpy()
    fc = df["fc_precipitation"].to_numpy()
    buf = np.zeros(N, bool)
    for a, b in STORMS.values():
        buf |= (idx >= pd.Timestamp(a, tz="UTC") - BUFFER) & (idx <= pd.Timestamp(b, tz="UTC") + BUFFER)
    train_h = (idx < pd.Timestamp("2024-01-01", tz="UTC")) & ~buf
    test_h = idx >= pd.Timestamp("2024-01-01", tz="UTC")

    sm = df["soil_moisture_7_to_28cm"].to_numpy()
    sm_tr = np.sort(sm[train_h & np.isfinite(sm)])
    ssi = np.searchsorted(sm_tr, np.nan_to_num(sm, nan=np.nanmedian(sm_tr))) / max(len(sm_tr), 1)
    snow72 = pd.Series(df["snowfall"].fillna(0)).rolling(72, min_periods=1).sum().to_numpy()
    p50, p95 = (float(np.nanquantile(y_raw[train_h], q)) for q in (0.5, 0.95))
    s = max(p95 - p50, 0.02)                      # river's own TRAIN level spread (m)
    c = CATCH.get(slug, {})
    tc = c.get("kirpich_tc_h") if not c.get("dem_unreliable") else None
    L = int(round(tc)) if tc else empirical_lag(rain, y, train_h)["to_peak"]["lag_h"]
    nrfa = c.get("nrfa") or {}
    desc = {"log_area": np.log10(c.get("nrfa_area_km2") or c.get("dem_area_km2") or 50), "tc": tc or L,
            "bfihost": nrfa.get("bfihost", np.nan), "saar": nrfa.get("saar-1961-1990", np.nan)}

    def ok(o):
        if o < CTX or o + H >= N:
            return False
        w = y_raw[o - CTX + 1:o + 1]
        return np.isnan(w).mean() <= 0.10 and np.isfinite(y[o])

    train_o = [o for o in np.where(train_h)[0][::6] if ok(o)]
    test_o = [o for o in np.where(test_h)[0][::3] if ok(o)]
    if not test_o:
        test_o = []

    cache = OUT / f"{slug}_tfm.npz"
    all_o = np.array(sorted(set(train_o) | set(test_o)))
    if cache.exists() and np.array_equal(np.load(cache)["o"], all_o):
        tr = np.load(cache)["traj"]
    else:
        ctx = [pd.Series(y[o - CTX + 1:o + 1]).interpolate(limit_area="inside").ffill().bfill().to_numpy(np.float32)
               for o in all_o]
        pt, _ = tfm().forecast(horizon=H, inputs=ctx)
        tr = np.asarray(pt)[:, -H:]
        np.savez_compressed(cache, o=all_o, traj=tr)
    traj = dict(zip(all_o.tolist(), tr))

    cs_r, cs_f = csum(rain), csum(fc)
    fc_ok = np.isfinite(fc)
    rmax6 = pd.Series(rain).rolling(6, min_periods=1).max().to_numpy()
    fut_max = {m: pd.Series(rain).rolling(m).max().shift(-m).to_numpy() for m in range(1, 7)}
    fc_max = {m: pd.Series(np.nan_to_num(fc)).rolling(m).max().shift(-m).to_numpy() for m in range(1, 7)}

    def rows(origins, variant):
        o = np.repeat(np.asarray(origins), H)
        h = np.tile(np.arange(1, H + 1), len(origins))
        t = o + h
        tp = np.stack([traj[x] for x in origins]).ravel()
        X = {"h": h, "y0n": (y[o] - p50) / s, "dy1n": (y[o] - y[o - 1]) / s, "dy3n": (y[o] - y[o - 3]) / s,
             "dy6n": (y[o] - y[o - 6]) / s, "dy24n": (y[o] - y[o - 24]) / s, "tfmn": (tp - p50) / s,
             "tfm_minus_y0n": (tp - y[o]) / s, "snow72": snow72[o], "ssi": ssi[o],
             "runoff_force_past": ssi[o] * rmax6[o] ** 2}
        for k in (1, 3, 6, 12, 24, 48, 72):
            X[f"rain_past_{k}"] = wsum(cs_r, o - k + 1, o)
        mwin = np.minimum(h, 6)
        a, b = t - L - 3, t - L + 3
        X["arrival_rain_obs"] = wsum(cs_r, a, np.minimum(b, o))
        if variant == "past":
            fs, fm, af = np.zeros(len(o)), np.zeros(len(o)), np.zeros(len(o))
        elif variant == "oracle":
            fs, fm, af = wsum(cs_r, o + 1, t), np.array([fut_max[m][x] for m, x in zip(mwin, o)]), wsum(cs_r, np.maximum(a, o + 1), b)
        else:
            fs, fm, af = wsum(cs_f, o + 1, t), np.array([fc_max[m][x] for m, x in zip(mwin, o)]), wsum(cs_f, np.maximum(a, o + 1), b)
        X["rain_future_sum"], X["runoff_force_future"], X["arrival_rain_future"] = fs, ssi[o] * np.nan_to_num(fm) ** 2, af
        for k, v in desc.items():
            X[k] = np.full(len(o), v)
        target = y_raw[np.minimum(t, N - 1)]
        valid = np.isfinite(target)
        if variant == "deployed":
            valid &= np.array([fc_ok[x + 1:x + H + 1].all() for x in o])
        return {"X": pd.DataFrame(X), "y": target, "tfm": tp, "y0": y[o], "h": h, "valid": valid}

    return {"slug": slug, "s": s, "p50": p50, "p95": p95, "train": rows(train_o, "oracle"),
            "test": {v: rows(test_o, v) for v in ("deployed", "past")} if test_o else {}}


DESC = ["log_area", "tc", "bfihost", "saar"]


def fit(parts: list[dict], with_desc: bool):
    X = pd.concat([p["train"]["X"] for p in parts], ignore_index=True)
    r = np.concatenate([(p["train"]["y"] - p["train"]["tfm"]) / p["s"] for p in parts])
    v = np.concatenate([p["train"]["valid"] for p in parts])
    if not with_desc:
        X = X.drop(columns=DESC)
    rf = X["runoff_force_past"] + X["runoff_force_future"]
    w = np.ones(len(X))
    w[rf.to_numpy() >= np.quantile(rf[v], 0.9)] = 5.0
    m = HistGradientBoostingRegressor(loss="quantile", quantile=0.6, max_iter=300, learning_rate=0.06,
                                      max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=1.0, random_state=0)
    m.fit(X[v], r[v], sample_weight=w[v])
    return m, list(X.columns)


def score(p: dict, preds: dict, var: str) -> dict:
    d = p["test"][var]
    v = d["valid"]
    surge = v & (d["y"] > p["p95"])
    out = {"rows": int(v.sum()), "surge_rows": int(surge.sum())}
    for k, pr in preds.items():
        e = np.abs(pr - d["y"])
        out[k] = {"mae": float(e[v].mean()), "surge_mae": float(e[surge].mean()) if surge.any() else None,
                  "mae_h": {hh: float(e[v & (d["h"] == hh)].mean()) for hh in (6, 12, 24)}}
    return out


def main():
    t0 = time.time()
    parts = {}
    for g in GAUGES:
        t1 = time.time()
        parts[g] = build(g)
        print(f"built {g}: {len(parts[g]['train']['y'])//H} train / {len(parts[g]['test'].get('deployed', {}).get('y', []))//H} test origins "
              f"({time.time() - t1:.0f}s)", flush=True)
    results = {}
    for g, p in parts.items():
        if not p["test"]:
            continue
        others = [q for k, q in parts.items() if k != g]
        models = {"pooled": fit(others, False), "pooled_desc": fit(others, True), "in_river": fit([p], False)}
        res = {}
        for var in ("deployed", "past"):
            d = p["test"][var]
            preds = {"persistence": d["y0"], "timesfm": d["tfm"]}
            for name, (m, cols) in models.items():
                preds[name] = d["tfm"] + p["s"] * m.predict(d["X"][cols])
            res[var] = score(p, preds, var)
        results[g] = res
        r = res["deployed"]
        print(f"{g}: MAE timesfm {r['timesfm']['mae']*1000:.0f} | in-river {r['in_river']['mae']*1000:.0f} | "
              f"UNSEEN pooled {r['pooled']['mae']*1000:.0f} | pooled+catch {r['pooled_desc']['mae']*1000:.0f} mm", flush=True)
    (OUT / "loro.json").write_text(json.dumps(results, indent=1))
    print(f"done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()

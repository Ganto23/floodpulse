"""
FloodPulse stress test: storms, DEM lag features, surge booster, lead-time warnings.

Splits (per gauge)
  TRAIN    hours < 2024-01-01, excluding storm windows ±7 days      (origins every 3 h)
  TEST     2024 (hourly origins) + held-out storms (hourly origins)
             ciara_dennis  2020-02-05 → 2020-02-25   (Storm Ciara 9 Feb, Storm Dennis 15-16 Feb)
             babet         2023-10-17 → 2023-10-25   (Storm Babet 18-21 Oct)

Inputs at origin τ (real-time valid unless marked)
  y history; observed rain (EA tipping-bucket gauges, ERA5 where a gauge gap exists);
  soil saturation index SSI = percentile of ERA5 7–28 cm soil moisture (TRAIN distribution);
  72 h snowfall; TimesFM 2.5 zero-shot trajectory (512 h context)
  future rain over (τ, τ+h], one of three variants:
    past        none
    oracle      actually-observed future rain: a PERFECT-FORECAST upper bound
    deployed    archived issued day-ahead NWP forecast (2024 only); booster trained on observed rain

Physics features (Phases 3-4)
  runoff_force      SSI · (max hourly rain intensity)²   (past 6 h and next min(h,6) h)
  arrival_rain      rain in the ±3 h window one DEM Kirpich lag (Tc) before the target hour,
                    split into the observed part and the future part

Models (target y(τ+h), h = 1..24)
  persistence, timesfm,
  booster       TimesFM + HistGradientBoosting on the TimesFM residual (quantile loss q=0.6,
                sample weight ×5 when runoff_force is in its TRAIN top decile)
  booster_nophys  same without runoff_force / arrival_rain / SSI  (ablation for Phases 3-4)

Metrics
  MAE overall and on surge hours (actual > TRAIN P95)
  crest capture per storm×gauge at leads 3/6/12 h before the real crest: magnitude error as % of
    the rise (crest − level at origin), timing error (h); capture = |mag| ≤ 20% and |timing| ≤ 3 h
  warnings: threshold θ = TRAIN P99 level; for each real up-crossing, sustained-warning lead time
    (hours before the crossing from which every hourly forecast predicts ≥ θ within 24 h);
    false-alarm ratio over 2024 hourly origins
Output: results/floodpulse/<gauge>.json
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

warnings.filterwarnings("ignore")
ROOT = Path(__file__).parent
RIVERS = ROOT / "data" / "rivers"
RES = ROOT / "results" / "floodpulse"
CTX, H = 512, 24
STORMS = {"ciara_dennis": ("2020-02-05", "2020-02-25 23:00"), "babet": ("2023-10-17", "2023-10-25 23:00")}
BUFFER = pd.Timedelta(days=7)
LEADS_CREST = (3, 6, 12)
GAUGES = ["calder_mytholmroyd", "cragg_dauber_bridge", "aire_armley", "calder_whalley", "eden_sheepmount",
          "greta_low_briery", "wharfe_otley", "ribble_samlesbury", "kent_victoria_bridge", "derwent_ouse_bridge"]

_MODEL = None


def tfm():
    global _MODEL
    if _MODEL is None:
        import timesfm
        _MODEL = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
        _MODEL.compile(timesfm.ForecastConfig(max_context=CTX, max_horizon=128, normalize_inputs=True,
                                              per_core_batch_size=128, use_continuous_quantile_head=True,
                                              fix_quantile_crossing=True))
    return _MODEL


def csum(a: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.nan_to_num(a))])


def wsum(cs: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Sum of a[lo..hi] inclusive (vectorized); empty when hi < lo."""
    n = len(cs) - 1
    lo_c, hi_c = np.clip(lo, 0, n), np.clip(hi + 1, 0, n)
    return np.where(hi >= lo, cs[np.maximum(hi_c, lo_c)] - cs[lo_c], 0.0)


def empirical_lag(rain: np.ndarray, y: np.ndarray, mask: np.ndarray) -> dict:
    """Lag (h) maximizing corr(rain(t−k), rise(t)), on TRAIN hours only."""
    s = pd.Series(y)
    rise = (s - s.rolling(168, min_periods=24).min()).to_numpy()   # level above 7-day baseline
    rate = s.diff().to_numpy()
    r3 = pd.Series(rain).rolling(3, min_periods=1).sum().to_numpy()
    out = {}
    for name, target in (("to_peak", rise), ("to_max_rate", rate)):
        best = (0, -1.0)
        for k in range(0, 73):
            x = np.roll(r3, k)
            m = mask & np.isfinite(x) & np.isfinite(target)
            m[:k] = False
            if m.sum() > 500:
                c = np.corrcoef(x[m], target[m])[0, 1]
                if c > best[1]:
                    best = (k, c)
        out[name] = {"lag_h": best[0], "r": round(float(best[1]), 3)}
    return out


def run(slug: str, catch: dict) -> dict:
    t_start = time.time()
    df = pd.read_csv(RIVERS / f"{slug}.csv", index_col="time", parse_dates=True).astype(float)
    idx = df.index
    N = len(df)
    y_raw = df["y"].to_numpy()
    y = df["y"].interpolate(limit=6, limit_area="inside").to_numpy()
    rain = df["ea_rain"].where(df["ea_rain"].notna(), df["precipitation"]).fillna(0).to_numpy()
    fc = df["fc_precipitation"].to_numpy()

    in_storm_buf = np.zeros(N, bool)
    storm_mask = {}
    for k, (a, b) in STORMS.items():
        in_storm_buf |= (idx >= pd.Timestamp(a, tz="UTC") - BUFFER) & (idx <= pd.Timestamp(b, tz="UTC") + BUFFER)
        storm_mask[k] = (idx >= pd.Timestamp(a, tz="UTC")) & (idx <= pd.Timestamp(b, tz="UTC"))
    train_h = (idx < pd.Timestamp("2024-01-01", tz="UTC")) & ~in_storm_buf
    test24 = idx >= pd.Timestamp("2024-01-01", tz="UTC")

    sm = df["soil_moisture_7_to_28cm"].to_numpy()
    sm_train = np.sort(sm[train_h & np.isfinite(sm)])
    ssi = np.searchsorted(sm_train, np.nan_to_num(sm, nan=np.nanmedian(sm_train))) / max(len(sm_train), 1)
    snow72 = pd.Series(df["snowfall"].fillna(0)).rolling(72, min_periods=1).sum().to_numpy()

    p95 = float(np.nanquantile(y_raw[train_h], 0.95))
    p99 = float(np.nanquantile(y_raw[train_h], 0.99))
    lag = empirical_lag(rain, y, train_h)
    tc = catch.get("kirpich_tc_h") if catch and not catch.get("dem_unreliable") else None
    L = int(round(tc)) if tc else lag["to_peak"]["lag_h"]

    def ok_origin(o):
        if o < CTX or o + H >= N:
            return False
        c = y_raw[o - CTX + 1:o + 1]
        return np.isnan(c).mean() <= 0.10 and np.isfinite(y[o])

    train_o = [o for o in np.where(train_h)[0][::3] if ok_origin(o)]
    test_o = {"2024": [o for o in np.where(test24)[0] if ok_origin(o)]}
    for k, m in storm_mask.items():
        cov = np.isfinite(y_raw[m]).mean() if m.any() else 0
        if cov >= 0.8:
            test_o[k] = [o for o in np.where(m)[0] if ok_origin(o)]
    all_o = sorted(set(train_o) | {o for v in test_o.values() for o in v})
    if not train_o or len(train_o) < 500:
        return {"gauge": slug, "skipped": f"only {len(train_o)} training origins"}

    # ---- TimesFM zero-shot trajectories -----------------------------------
    t0 = time.time()
    ctx = [pd.Series(y[o - CTX + 1:o + 1]).interpolate(limit_area="inside").ffill().bfill().to_numpy(np.float32)
           for o in all_o]
    pt, _ = tfm().forecast(horizon=H, inputs=ctx)
    traj = dict(zip(all_o, np.asarray(pt)[:, -H:]))
    t_tfm = time.time() - t0

    # ---- feature rows ------------------------------------------------------
    cs_r, cs_f = csum(rain), csum(fc)
    fc_ok = np.isfinite(fc)
    rmax6_past = pd.Series(rain).rolling(6, min_periods=1).max().to_numpy()
    rain_s = pd.Series(rain)
    fut_max = {m: rain_s.rolling(m).max().shift(-m).to_numpy() for m in range(1, 7)}
    fc_s = pd.Series(np.nan_to_num(fc))
    fc_max = {m: fc_s.rolling(m).max().shift(-m).to_numpy() for m in range(1, 7)}
    hh = np.arange(1, H + 1)

    def rows(origins, variant):
        o = np.repeat(np.asarray(origins), H)
        h = np.tile(hh, len(origins))
        t = o + h
        tp = np.stack([traj[x] for x in origins]).ravel()
        X = {
            "h": h, "y0": y[o], "dy1": y[o] - y[o - 1], "dy3": y[o] - y[o - 3], "dy6": y[o] - y[o - 6],
            "dy24": y[o] - y[o - 24], "tfm": tp, "tfm_minus_y0": tp - y[o], "snow72": snow72[o],
        }
        for k in (1, 3, 6, 12, 24, 48, 72):
            X[f"rain_past_{k}"] = wsum(cs_r, o - k + 1, o)
        X["ssi"] = ssi[o]
        X["runoff_force_past"] = ssi[o] * rmax6_past[o] ** 2
        mwin = np.minimum(h, 6)
        a, b = t - L - 3, t - L + 3
        X["arrival_rain_obs"] = wsum(cs_r, a, np.minimum(b, o))
        if variant == "past":
            fut_sum, fut_mx, arr_fut = np.zeros(len(o)), np.zeros(len(o)), np.zeros(len(o))
        elif variant == "oracle":
            fut_sum = wsum(cs_r, o + 1, t)
            fut_mx = np.array([fut_max[m][x] for m, x in zip(mwin, o)])
            arr_fut = wsum(cs_r, np.maximum(a, o + 1), b)
        else:   # deployed: issued forecasts
            fut_sum = wsum(cs_f, o + 1, t)
            fut_mx = np.array([fc_max[m][x] for m, x in zip(mwin, o)])
            arr_fut = wsum(cs_f, np.maximum(a, o + 1), b)
        X["rain_future_sum"] = fut_sum
        X["runoff_force_future"] = ssi[o] * np.nan_to_num(fut_mx) ** 2
        X["arrival_rain_future"] = arr_fut
        Xdf = pd.DataFrame(X)
        target = y_raw[np.minimum(t, N - 1)]
        valid = np.isfinite(target)
        if variant == "deployed":
            valid &= np.array([fc_ok[x + 1:x + H + 1].all() for x in o])
        return Xdf, target, tp, o, h, t, valid

    PHYS = ["ssi", "runoff_force_past", "runoff_force_future", "arrival_rain_obs", "arrival_rain_future"]

    def fit_booster(variant_train, drop=()):
        Xd, yt, tp, *_ , valid = rows(train_o, variant_train)
        Xd = Xd.drop(columns=list(drop))
        rf = (Xd.get("runoff_force_past", 0) + Xd.get("runoff_force_future", 0)) if "runoff_force_past" in Xd else None
        w = np.ones(len(Xd))
        if rf is not None:
            w[rf.to_numpy() >= np.quantile(rf[valid], 0.9)] = 5.0
        mdl = HistGradientBoostingRegressor(loss="quantile", quantile=0.6, max_iter=300, learning_rate=0.06,
                                            max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=1.0,
                                            random_state=0)
        mdl.fit(Xd[valid], (yt - tp)[valid], sample_weight=w[valid])
        return mdl, list(Xd.columns)

    t0 = time.time()
    boosters = {
        "past": fit_booster("past"),
        "oracle": fit_booster("oracle"),
        "oracle_nophys": fit_booster("oracle", drop=PHYS),
        "past_nophys": fit_booster("past", drop=PHYS),
    }
    t_fit = time.time() - t0

    def predict_all(origins, variant):
        Xd, yt, tp, o, h, t, valid = rows(origins, variant)
        train_variant = "oracle" if variant == "deployed" else variant
        out = {"persistence": y[o], "timesfm": tp}
        m, cols = boosters[train_variant]
        out["booster"] = tp + m.predict(Xd[cols])
        m2, cols2 = boosters[f"{train_variant}_nophys"]
        out["booster_nophys"] = tp + m2.predict(Xd[cols2])
        return out, yt, o, h, t, valid

    result = {"gauge": slug, "river": catch.get("river") if catch else None,
              "p95": p95, "p99_threshold": p99, "dem_lag_h": tc, "lag_used_h": L, "empirical_lag": lag,
              "n_train_origins": len(train_o), "seconds": {"timesfm": round(t_tfm, 1), "fit": round(t_fit, 1)},
              "sets": {}}

    for set_name, origins in test_o.items():
        if not origins:
            continue
        variants = ["past", "oracle"] + (["deployed"] if set_name == "2024" else [])
        sres = {"origins": len(origins), "variants": {}}
        for var in variants:
            preds, yt, o, h, t, valid = predict_all(origins, var)
            if valid.sum() < 100:
                continue
            vres = {"rows": int(valid.sum())}
            surge = valid & (yt > p95)
            for mname, p in preds.items():
                e = np.abs(p - yt)
                vres[mname] = {
                    "mae": float(e[valid].mean()),
                    "mae_h": {hh_: float(e[valid & (h == hh_)].mean()) for hh_ in (6, 12, 24)},
                    "surge_mae": float(e[surge].mean()) if surge.any() else None,
                    "surge_bias": float((p - yt)[surge].mean()) if surge.any() else None,
                    "surge_rows": int(surge.sum()),
                }
            vres["crest"] = crest_metrics(preds, yt, o, h, t, valid, origins, y_raw, idx, set_name)
            vres["warning"] = warning_metrics(preds, yt, o, h, t, valid, origins, y_raw, p99, set_name)
            sres["variants"][var] = vres
        result["sets"][set_name] = sres
    result["seconds"]["total"] = round(time.time() - t_start, 1)
    return result


def _trajectories(preds, o, h, valid, origins):
    """{model: {origin: array(H)}} with NaN where invalid."""
    out = {}
    pos = {x: i for i, x in enumerate(origins)}
    for m, p in preds.items():
        arr = np.full((len(origins), H), np.nan)
        rows = np.arange(len(o))
        arr[[pos[x] for x in o], h - 1] = np.where(valid, p, np.nan)
        out[m] = arr
    return out, pos


def crest_metrics(preds, yt, o, h, t, valid, origins, y_raw, idx, set_name):
    if set_name == "2024":
        return None
    traj, pos = _trajectories(preds, o, h, valid, origins)
    win = np.array(origins)
    lo, hi = win.min(), win.max() + H
    seg = y_raw[lo:hi + 1]
    if not np.isfinite(seg).any():
        return None
    tc = lo + int(np.nanargmax(seg))
    crest = float(y_raw[tc])
    res = {"crest_time": str(idx[tc]), "crest_m": crest, "leads": {}}
    for L in LEADS_CREST:
        oo = tc - L
        if oo not in pos:
            continue
        base = y_raw[oo]
        rise = crest - base
        lr = {"rise_m": float(rise)}
        for m, arr in traj.items():
            tr = arr[pos[oo]]
            if not np.isfinite(tr).any():
                continue
            pk = int(np.nanargmax(tr))
            mag = float(np.nanmax(tr) - crest)
            timing = (oo + pk + 1) - tc
            mag_pct = mag / rise if rise > 0.05 else None
            lr[m] = {"peak_err_m": mag, "peak_err_pct_of_rise": mag_pct, "timing_err_h": int(timing),
                     "captured": bool(mag_pct is not None and abs(mag_pct) <= 0.2 and abs(timing) <= 3)}
        res["leads"][L] = lr
    return res


def warning_metrics(preds, yt, o, h, t, valid, origins, y_raw, thr, set_name):
    traj, pos = _trajectories(preds, o, h, valid, origins)
    win = np.array(origins)
    # real up-crossings of θ inside the evaluated window, ≥48 h apart
    cross = []
    for c in range(win.min() + 1, win.max() + 1):
        if np.isfinite(y_raw[c]) and np.isfinite(y_raw[c - 1]) and y_raw[c - 1] < thr <= y_raw[c]:
            if not cross or c - cross[-1] >= 48:
                cross.append(c)
    out = {"threshold_m": thr, "events": len(cross), "models": {}}
    for m, arr in traj.items():
        warn = np.nanmax(np.where(np.isnan(arr), -np.inf, arr), axis=1) >= thr
        leads, hits = [], 0
        for c in cross:
            lead = 0
            for L in range(1, H + 1):          # sustained: every origin from c−L … c−1 warns
                oo = c - L
                if oo in pos and warn[pos[oo]]:
                    lead = L
                else:
                    break
            leads.append(lead)
            hits += lead > 0
        # false alarms: warnings where no real exceedance occurs in the next 24 h
        fa = tot = 0
        for x, i in pos.items():
            if warn[i]:
                tot += 1
                fut = y_raw[x + 1:x + H + 1]
                fa += not (np.isfinite(fut) & (fut >= thr)).any()
        out["models"][m] = {"hit_rate": hits / len(cross) if cross else None,
                            "mean_lead_h": float(np.mean(leads)) if cross else None,
                            "leads_h": leads, "warnings": tot, "false_alarm_ratio": fa / tot if tot else None}
    return out


if __name__ == "__main__":
    RES.mkdir(parents=True, exist_ok=True)
    catch = json.loads((RIVERS / "catchments.json").read_text())
    catch["cragg_dauber_bridge"]["dem_unreliable"] = True   # snapped onto the Calder (no NRFA reference)
    for slug in sys.argv[1:] or GAUGES:
        t0 = time.time()
        try:
            r = run(slug, catch.get(slug, {}))
        except Exception as exc:
            import traceback
            r = {"gauge": slug, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-1500:]}
        (RES / f"{slug}.json").write_text(json.dumps(r, indent=1, default=str))
        print(f"== {slug} done in {time.time() - t0:.0f}s: "
              f"{r.get('error') or r.get('skipped') or list(r['sets'])}", flush=True)

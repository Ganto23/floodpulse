"""
GridPulse: can NESO's day-ahead error be predicted before it happens?

Target: residual(t) = INDO(t) − NESO day-ahead forecast(t).
Lead h ∈ {1, 3, 6}: the decision is made at τ = t − h. Information allowed at τ:
  * residuals for hours that have ENDED by τ (hour index ≤ t − h − 1)
  * NESO forecasts published by τ                 → ndf_l{h}
  * actual weather up to τ (ERA5, a stand-in for live observations)
  * weather forecasts issued earlier                → fc_* (incl. for hour t)

Models (TEST = last 30%, rolling hourly)
  neso_da        residual prediction 0 (accept the day-ahead forecast)
  neso_latest    NESO's own revision: ndf_l{h} − ndf_da         ← the bar that matters
  persistence    last known residual
  timesfm        TimesFM 2.5 zero-shot on the residual series (512 h context)
  timesfm+xreg   TimesFM + issued weather forecasts and NESO day-ahead level as covariates
  ridge          linear model fit on DEV: residual lags, NESO revision, latest weather
                 surprise, issued weather forecast for t, hour of day
Scored: MAE of the corrected demand forecast (MW), skill vs neso_da and vs neso_latest,
directional accuracy (sign of NESO's error), also on larger-than-median errors.
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from test_timesfm import fill, load_model

warnings.filterwarnings("ignore")
ROOT = Path(__file__).parent
DEV_FRAC, CONTEXT, LEADS = 0.7, 512, (1, 3, 6)
WX = ["temperature_2m", "shortwave_radiation", "cloud_cover"]


def load() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / "gridpulse.csv", index_col="time", parse_dates=True).astype(float)
    for v in WX:
        df[f"surprise_{v}"] = df[v] - df[f"fc_{v}"]
    return df


WEATHER_PREFIXES = ("surprise_", "fc_")


def ridge_design(df: pd.DataFrame, h: int, latency: int = 0) -> pd.DataFrame:
    """Row t = features available at τ = t − h for predicting residual(t).
    latency = extra hours before an outturn is usable (sensitivity check)."""
    r = df["residual"]
    k = h + 1 + latency                         # most recent hour fully ended (and published) by τ
    cols = {f"res_l{k + j}": r.shift(k + j) for j in (0, 1, 2, 23 - k if 23 - k > 2 else 3)}
    cols["res_l24"] = r.shift(max(24, k))
    cols["neso_revision"] = df[f"ndf_l{h}"] - df["ndf_da"]
    for v in WX:
        cols[f"surprise_{v}_now"] = df[f"surprise_{v}"].shift(k)        # latest observed surprise
        cols[f"fc_{v}_t"] = df[f"fc_{v}"]                               # issued forecast for t
        cols[f"fc_{v}_change"] = df[f"fc_{v}"] - df[f"fc_{v}"].shift(k)
    hr = df.index.hour
    cols["hour_sin"], cols["hour_cos"] = np.sin(2 * np.pi * hr / 24), np.cos(2 * np.pi * hr / 24)
    return pd.DataFrame(cols, index=df.index)


def fit_ridge(X: pd.DataFrame, y: pd.Series, alpha: float = 1.0):
    mu, sd = X.mean(), X.std().replace(0, 1)
    Z = np.column_stack([np.ones(len(X)), ((X - mu) / sd).values])
    reg = alpha * np.eye(Z.shape[1]); reg[0, 0] = 0
    beta = np.linalg.solve(Z.T @ Z + reg, Z.T @ y.values)
    return lambda Xn: np.column_stack([np.ones(len(Xn)), ((Xn - mu) / sd).values]) @ beta


def padded(a: np.ndarray, start: int, stop: int) -> np.ndarray:
    seg = a[start:min(stop, len(a))]
    return np.concatenate([seg, np.full(stop - start - len(seg), seg[-1])]) if len(seg) < stop - start else seg


def score(pred: np.ndarray, act: np.ndarray, big: np.ndarray) -> dict:
    m = ~np.isnan(pred) & ~np.isnan(act)
    mae = float(np.abs(act[m] - pred[m]).mean())
    d = m & (pred != 0) & (act != 0)
    db = d & big
    return {"mae_mw": mae, "n": int(m.sum()),
            "direction": float((np.sign(pred[d]) == np.sign(act[d])).mean()) if d.any() else None,
            "direction_large": float((np.sign(pred[db]) == np.sign(act[db])).mean()) if db.any() else None}


def main() -> dict:
    df = load()
    T = len(df)
    dev_n = int(T * DEV_FRAC)
    resid = df["residual"].to_numpy()
    big_thr = np.nanmedian(np.abs(resid[:dev_n]))

    # TimesFM: one forecast per context end c (last known hour), horizon max(LEADS)+1.
    # Target t = c + 1 + h uses step h + 1.
    c_ends = [c for c in range(dev_n - max(LEADS) - 1, T - 1) if c - CONTEXT >= 0]
    ctx = [fill(resid[c - CONTEXT + 1:c + 1]) for c in c_ends]
    H = max(LEADS) + 1
    model = load_model()
    t0 = time.time()
    point, _ = model.forecast(horizon=H, inputs=ctx)
    point = np.asarray(point)[:, -H:]
    t_tfm = time.time() - t0

    covs = ["fc_temperature_2m", "fc_shortwave_radiation", "fc_cloud_cover", "ndf_da"]
    t0 = time.time()
    try:
        cov = {c: [fill(padded(df[c].to_numpy(), e - CONTEXT + 1, e + 1 + H)) for e in c_ends] for c in covs}
        xp, _ = model.forecast_with_covariates(inputs=ctx, dynamic_numerical_covariates=cov,
                                               xreg_mode="xreg + timesfm", ridge=1.0)
        xpoint = np.stack([np.asarray(p)[-H:] for p in xp])
        xreg_note = f"covariates {covs}"
    except Exception as exc:
        xpoint, xreg_note = None, f"failed: {type(exc).__name__}: {exc}"[:200]
    t_x = time.time() - t0

    out = {"dev_end": str(df.index[dev_n]), "test_hours": T - dev_n, "context_h": CONTEXT,
           "big_error_threshold_mw": float(big_thr), "xreg": xreg_note,
           "seconds": {"timesfm": round(t_tfm, 1), "xreg": round(t_x, 1)}, "leads": {}}
    c_index = {c: i for i, c in enumerate(c_ends)}

    for h in LEADS:
        targets = np.arange(dev_n, T)
        act = resid[targets]
        big = np.abs(act) > big_thr
        preds = {"neso_da": np.zeros(len(targets)),
                 "neso_latest": (df[f"ndf_l{h}"] - df["ndf_da"]).to_numpy()[targets],
                 "persistence": resid[targets - h - 1]}
        tf, xf = np.full(len(targets), np.nan), np.full(len(targets), np.nan)
        for j, t in enumerate(targets):
            i = c_index.get(t - h - 1)
            if i is not None:
                tf[j] = point[i, h]
                if xpoint is not None:
                    xf[j] = xpoint[i, h]
        preds["timesfm"] = tf
        if xpoint is not None:
            preds["timesfm+xreg"] = xf

        def ridge_variant(cols_filter, latency=0):
            X = ridge_design(df, h, latency)
            X = X[[c for c in X.columns if cols_filter(c)]]
            ok = X.notna().all(1) & df["residual"].notna()
            devmask = ok & (np.arange(T) < dev_n)
            f = fit_ridge(X[devmask], df["residual"][devmask])
            rp = np.full(T, np.nan)
            rp[ok.to_numpy()] = f(X[ok])
            return rp[targets]

        is_wx = lambda c: c.startswith(WEATHER_PREFIXES)
        preds["ridge"] = ridge_variant(lambda c: True)
        preds["ridge_no_weather"] = ridge_variant(lambda c: not is_wx(c))
        preds["ridge_weather_only"] = ridge_variant(lambda c: is_wx(c) or c.startswith("hour_"))
        preds["ridge_latency+1h"] = ridge_variant(lambda c: True, latency=1)

        # score every model on the hours where ALL models have a prediction
        common = ~np.isnan(act)
        for p in preds.values():
            common &= ~np.isnan(p)
        res = {m: score(np.where(common, p, np.nan), np.where(common, act, np.nan), big) for m, p in preds.items()}
        base_da, base_latest = res["neso_da"]["mae_mw"], res["neso_latest"]["mae_mw"]
        for m in res:
            res[m]["skill_vs_neso_da"] = 1 - res[m]["mae_mw"] / base_da
            res[m]["skill_vs_neso_latest"] = 1 - res[m]["mae_mw"] / base_latest
        out["leads"][h] = res
    return out


def show(r: dict) -> None:
    print(f"\n{'=' * 96}\nPREDICTING NESO'S DAY-AHEAD ERROR  (TEST from {r['dev_end'][:10]}, {r['test_hours']} h)")
    print(f"   xreg: {r['xreg']}  | TimesFM {r['seconds']['timesfm']}s")
    for h, res in r["leads"].items():
        print(f"\n   lead {h} h   {'MAE MW':>8s}{'vs NESO-DA':>12s}{'vs NESO-latest':>16s}{'direction':>11s}{'dir |e|>med':>13s}")
        for m, v in sorted(res.items(), key=lambda kv: kv[1]["mae_mw"]):
            d = f"{v['direction']:.1%}" if v["direction"] is not None else "—"
            dl = f"{v['direction_large']:.1%}" if v["direction_large"] is not None else "—"
            print(f"   {m:12s}{v['mae_mw']:8.0f}{v['skill_vs_neso_da']:+12.1%}{v['skill_vs_neso_latest']:+16.1%}{d:>11s}{dl:>13s}")


if __name__ == "__main__":
    r = main()
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "residuals_timesfm.json").write_text(json.dumps(r, indent=1, default=str))
    show(r)

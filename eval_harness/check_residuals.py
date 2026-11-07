"""
GridPulse residual analysis: does weather explain NESO's day-ahead demand forecast error?

residual = INDO − NESO day-ahead forecast (>0: NESO under-forecast demand)
DEV = first 70% of hours, TEST = last 30%. Thresholds and fitted rules use DEV only.

Weather features
  volatility (ex post)  temp_delta_3h, solar_delta_1h, cloud_delta_1h        (actual ERA5)
  surprise   (ex post)  temp/solar/cloud surprise = actual − issued day-ahead forecast
  "Ex post" means known only after the hour. These features explain errors; they can't trade them.
  test_timesfm_residuals.py checks what's predictable in advance.

Controls
  * every correlation also computed after removing the hour-of-day mean (DEV), because solar
    ramps and NESO's error size both follow the clock
  * p-values via effective sample size (autocorrelation)
  * event coincidence is reported as LIFT over the base rate, not a bare percentage
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from check_correlation import p_eff

ROOT = Path(__file__).parent
DEV_FRAC = 0.7


def load() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / "gridpulse.csv", index_col="time", parse_dates=True).astype(float)
    df["abs_residual"] = df["residual"].abs()
    df["temp_delta_3h"] = df["temperature_2m"].diff(3)
    df["solar_delta_1h"] = df["shortwave_radiation"].diff(1)
    df["cloud_delta_1h"] = df["cloud_cover"].diff(1)
    df["temp_surprise"] = df["temperature_2m"] - df["fc_temperature_2m"]
    df["solar_surprise"] = df["shortwave_radiation"] - df["fc_shortwave_radiation"]
    df["cloud_surprise"] = df["cloud_cover"] - df["fc_cloud_cover"]
    return df


FEATURES = ["temp_delta_3h", "solar_delta_1h", "cloud_delta_1h",
            "temp_surprise", "solar_surprise", "cloud_surprise"]


def hour_adjust(s: pd.Series, dev: pd.Series) -> pd.Series:
    clim = s[dev].groupby(s[dev].index.hour).mean()
    return s - clim.reindex(s.index.hour).to_numpy()


def corr_block(x: pd.Series, y: pd.Series) -> dict:
    m = x.notna() & y.notna()
    r = float(np.corrcoef(x[m], y[m])[0, 1])
    rho = float(stats.spearmanr(x[m], y[m]).statistic)
    p, n_eff = p_eff(r, int(m.sum()), float(x[m].autocorr(1)), float(y[m].autocorr(1)))
    return {"pearson": r, "spearman": rho, "p_eff": p, "n_eff": round(n_eff), "n": int(m.sum())}


def neso_baseline(df: pd.DataFrame) -> dict:
    out = {}
    for col, label in [("ndf_da", "day-ahead (10:00 D-1)"), ("ndf_l6", "latest ≥6h before"),
                       ("ndf_l3", "latest ≥3h before"), ("ndf_l1", "latest ≥1h before")]:
        e = (df["indo"] - df[col]).dropna()
        out[col] = {"label": label, "mae_mw": float(e.abs().mean()), "rmse_mw": float(np.sqrt((e ** 2).mean())),
                    "bias_mw": float(e.mean()),
                    "mape": float((e.abs() / df.loc[e.index, "indo"]).mean()), "hours": len(e)}
    by_hour = (df["abs_residual"].groupby(df.index.hour).mean()).round(0)
    out["mae_by_hour_of_day"] = by_hour.to_dict()
    return out


def analyse() -> dict:
    df = load()
    dev = pd.Series(np.arange(len(df)) < int(len(df) * DEV_FRAC), index=df.index)
    res = {"dev_end": str(df.index[dev.sum()]), "hours": len(df), "neso": neso_baseline(df)}

    # ---- correlations ------------------------------------------------------
    corr = {}
    for f in FEATURES:
        corr[f] = {
            "vs_abs_residual": corr_block(df[f], df["abs_residual"]),
            "vs_abs_residual_hour_adjusted": corr_block(hour_adjust(df[f], dev), hour_adjust(df["abs_residual"], dev)),
            "vs_signed_residual": corr_block(df[f], df["residual"]),
            "vs_signed_residual_hour_adjusted": corr_block(hour_adjust(df[f], dev), hour_adjust(df["residual"], dev)),
            # magnitude of the weather move vs magnitude of the error
            "abs_vs_abs_hour_adjusted": corr_block(hour_adjust(df[f].abs(), dev), hour_adjust(df["abs_residual"], dev)),
        }
    res["correlations"] = corr

    # ---- top-10% error events -----------------------------------------------
    p90 = df.loc[dev, "abs_residual"].quantile(0.9)
    big = df["abs_residual"] > p90
    events = {"p90_mw": float(p90), "event_hours": int(big.sum())}
    flags = {}
    for f in FEATURES:
        thr = df.loc[dev, f].abs().quantile(0.8)        # "rapid/large" = top 20% |feature| on DEV
        flags[f] = df[f].abs() > thr
    flags["any_volatility"] = flags["temp_delta_3h"] | flags["solar_delta_1h"] | flags["cloud_delta_1h"]
    flags["any_surprise"] = flags["temp_surprise"] | flags["solar_surprise"] | flags["cloud_surprise"]
    for name, fl in flags.items():
        valid = fl.notna() & df["abs_residual"].notna()
        in_events = float(fl[big & valid].mean())
        base = float(fl[valid].mean())
        events[name] = {"share_of_events": in_events, "base_rate": base,
                        "lift": in_events / base if base else None}
    res["events"] = events

    # ---- direction ---------------------------------------------------------
    # physics: more sun / warmer than forecast -> less demand -> NESO over-forecast (residual < 0)
    test = ~dev
    y = np.sign(df["residual"])
    direction = {}
    for f in ("solar_surprise", "temp_surprise", "cloud_surprise"):
        sign = -1 if f != "cloud_surprise" else +1     # more cloud than forecast -> more demand
        pred = sign * np.sign(df[f])
        m = test & pred.ne(0) & y.ne(0) & pred.notna() & y.notna()
        mb = m & (df["abs_residual"] > df.loc[dev, "abs_residual"].median())
        direction[f] = {"rule": f"sign(residual) = {'−' if sign < 0 else '+'}sign({f})",
                        "accuracy_test": float((pred[m] == y[m]).mean()),
                        "accuracy_test_large_errors": float((pred[mb] == y[mb]).mean()), "n": int(m.sum())}
    # logistic regression on all surprises + volatilities (fit DEV, score TEST)
    X = df[FEATURES]
    ok = X.notna().all(1) & y.ne(0) & y.notna()
    Xd, yd = X[ok & dev], (y[ok & dev] > 0).astype(int)
    Xt, yt = X[ok & test], (y[ok & test] > 0).astype(int)
    mu, sd = Xd.mean(), Xd.std()
    w = _logit((Xd - mu) / sd, yd)
    pt = 1 / (1 + np.exp(-(np.column_stack([np.ones(len(Xt)), ((Xt - mu) / sd).values]) @ w)))
    big_t = df.loc[Xt.index, "abs_residual"] > df.loc[dev, "abs_residual"].median()
    direction["logistic_all_features"] = {
        "accuracy_test": float(((pt > 0.5).astype(int) == yt).mean()),
        "accuracy_test_large_errors": float(((pt > 0.5).astype(int)[big_t.values] == yt[big_t]).mean()),
        "majority_baseline_test": float(max(yt.mean(), 1 - yt.mean())), "n": int(len(yt))}
    res["direction"] = direction
    return res


def _logit(X: pd.DataFrame, y: pd.Series, l2: float = 1e-2, iters: int = 200) -> np.ndarray:
    A = np.column_stack([np.ones(len(X)), X.values])
    w = np.zeros(A.shape[1])
    for _ in range(iters):   # Newton-Raphson with ridge
        p = 1 / (1 + np.exp(-A @ w))
        g = A.T @ (p - y.values) + l2 * np.r_[0, w[1:]]
        Hm = (A * (p * (1 - p))[:, None]).T @ A + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        w -= np.linalg.solve(Hm, g)
    return w


def show(r: dict) -> None:
    n = r["neso"]
    print(f"\n{'=' * 96}\nNESO FORECAST ACCURACY ({r['hours']} h)")
    for k in ("ndf_da", "ndf_l6", "ndf_l3", "ndf_l1"):
        v = n[k]
        print(f"   {v['label']:24s} MAE {v['mae_mw']:6.0f} MW  ({v['mape']:.2%})  RMSE {v['rmse_mw']:6.0f}  bias {v['bias_mw']:+6.0f}")
    print(f"\nCORRELATION WITH NESO DAY-AHEAD ERROR   (r / ρ ; * = p_eff<0.05)")
    print(f"   {'feature':16s}{'|err| raw':>16s}{'|err| hr-adj':>16s}{'|x| vs |err| adj':>18s}{'signed adj':>16s}")
    for f, c in r["correlations"].items():
        cell = lambda b: f"{b['pearson']:+.2f}/{b['spearman']:+.2f}{'*' if b['p_eff'] < 0.05 else ' '}"
        print(f"   {f:16s}{cell(c['vs_abs_residual']):>16s}{cell(c['vs_abs_residual_hour_adjusted']):>16s}"
              f"{cell(c['abs_vs_abs_hour_adjusted']):>18s}{cell(c['vs_signed_residual_hour_adjusted']):>16s}")
    e = r["events"]
    print(f"\nTOP-10% ERROR EVENTS (|residual| > {e['p90_mw']:.0f} MW, {e['event_hours']} h)")
    print(f"   {'large-move flag (top 20%)':28s}{'in events':>10s}{'all hours':>10s}{'lift':>7s}")
    for k, v in e.items():
        if isinstance(v, dict):
            print(f"   {k:28s}{v['share_of_events']:10.1%}{v['base_rate']:10.1%}{v['lift']:7.2f}x")
    print("\nDIRECTION OF NESO ERROR (TEST)")
    for k, v in r["direction"].items():
        extra = f" (majority-class baseline {v['majority_baseline_test']:.1%})" if "majority_baseline_test" in v else ""
        print(f"   {k:24s} accuracy {v['accuracy_test']:.1%} | on larger-than-median errors "
              f"{v['accuracy_test_large_errors']:.1%}{extra}")


if __name__ == "__main__":
    r = analyse()
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "residuals_analysis.json").write_text(json.dumps(r, indent=1, default=str))
    show(r)

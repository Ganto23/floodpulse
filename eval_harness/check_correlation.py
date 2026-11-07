"""
Statistical correlation engine.

For each idea (data/<idea>.csv, column y = target):
  * split: DEV = first 80% of hours, TEST = last 20% (all fits use DEV only)
  * two views:
      raw      — series as observed
      anomaly  — hour-of-week climatology (estimated on DEV) removed from y and every X.
                 Without this, the shared daily/weekly cycle produces large spurious
                 correlations (demand and temperature both follow the clock).
  * lagged Pearson r and Spearman ρ for corr(X_{t-k}, Y_t), k = 0..48 h
  * p-values from an effective sample size (Bretherton et al. 1999):
        n_eff = n · (1 − ρ1x·ρ1y) / (1 + ρ1x·ρ1y)
    Naive p-values on ~14k autocorrelated hourly points are meaningless.
  * Granger causality (statsmodels, lag 24) on stationary series (differenced if ADF p > 0.05)
  * linear regression R²: y on all X at their best lags, in-sample (DEV) and out-of-sample (TEST)
  * incremental predictive value: does X improve a 1-hour-ahead AR(24) model of y
    out of sample? (R²_TEST of [y lags] vs [y lags + X lags])

Run:  .venv/bin/python check_correlation.py   → results/correlation_<idea>.json + printed matrices
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import adfuller, grangercausalitytests

warnings.filterwarnings("ignore")
ROOT = Path(__file__).parent
LAGS = range(0, 49)
SHOW_LAGS = [0, 1, 2, 3, 6, 12, 24, 36, 48]
DEV_FRAC = 0.8


def load(name: str) -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / f"{name}.csv", index_col="time", parse_dates=True).astype(float)
    for f, (base, build) in DERIVED.items():   # derived forecast features from RAW issued forecasts
        if f in df and f"fc_{base}" in df:
            df[f"fc_{f}"] = build(df[f"fc_{base}"]).where(df[f"fc_{base}"].notna())
    return df


def deseasonalise(df: pd.DataFrame, dev_end: pd.Timestamp) -> pd.DataFrame:
    how = df.index.dayofweek * 24 + df.index.hour
    clim = df[df.index < dev_end].groupby(how[df.index < dev_end]).mean()
    for c in df.columns:   # issued forecasts are anomalised against the ACTUAL variable's climatology
        if c.startswith("fc_") and c[3:] in clim:
            clim[c] = clim[c[3:]]
    return df - clim.reindex(how).set_axis(df.index)


DERIVED = {  # derived feature -> (base var, builder from a precipitation/temperature series)
    "precip_6h": ("precipitation", lambda s: s.rolling(6, min_periods=1).sum()),
    "precip_24h": ("precipitation", lambda s: s.rolling(24, min_periods=1).sum()),
    "heating_degree": ("temperature_2m", lambda s: (15.5 - s).clip(lower=0)),
}


def forecastable(d: pd.DataFrame, features: list[str], test_mask) -> dict[str, str]:
    """feature -> issued-forecast column, for features with ≥90% forecast coverage in TEST."""
    out = {}
    for f in features:
        col = f"fc_{f}"
        if col in d and d.loc[test_mask, col].notna().mean() >= 0.9:
            out[f] = col
    return out


def lag1(s: pd.Series) -> float:
    return float(s.autocorr(1))


def p_eff(r: float, n: int, r1x: float, r1y: float) -> tuple[float, float]:
    prod = np.clip(r1x * r1y, -0.999, 0.999)
    n_eff = max(n * (1 - prod) / (1 + prod), 3.0)
    t = r * np.sqrt((n_eff - 2) / max(1 - r * r, 1e-12))
    return float(2 * stats.t.sf(abs(t), n_eff - 2)), float(n_eff)


def lag_table(d: pd.DataFrame, features: list[str]) -> dict:
    y = d["y"]
    ry = y.rank()
    out = {}
    for f in features:
        x, rx = d[f], d[f].rank()
        rows = []
        for k in LAGS:
            xs, rxs = x.shift(k), rx.shift(k)
            m = y.notna() & xs.notna()
            n = int(m.sum())
            if n < 100:
                rows.append({"lag": k, "pearson": None, "spearman": None, "n": n})
                continue
            rows.append({"lag": k, "pearson": float(np.corrcoef(xs[m], y[m])[0, 1]),
                         "spearman": float(np.corrcoef(rxs[m], ry[m])[0, 1]), "n": n})
        valid = [r for r in rows if r["pearson"] is not None and r["lag"] >= 1]
        best = max(valid, key=lambda r: abs(r["pearson"]))
        p, n_eff = p_eff(best["pearson"], best["n"], lag1(x.dropna()), lag1(y.dropna()))
        out[f] = {"rows": rows, "best_lag": best["lag"], "best_pearson": best["pearson"],
                  "best_spearman": best["spearman"], "p_eff": p, "n_eff": round(n_eff, 1)}
    return out


def stationary(s: pd.Series) -> tuple[pd.Series, bool]:
    s = s.interpolate(limit=6).dropna()
    p = adfuller(s.iloc[:: max(1, len(s) // 6000)], autolag="AIC")[1]
    return (s.diff().dropna(), True) if p > 0.05 else (s, False)


def granger(d: pd.DataFrame, f: str, lag: int = 24) -> dict:
    y, dy = stationary(d["y"])
    x, dx = stationary(d[f])
    pair = pd.concat([y, x], axis=1, join="inner").dropna()
    res = grangercausalitytests(pair.values, maxlag=[lag])
    F, p = res[lag][0]["ssr_ftest"][:2]
    return {"lag": lag, "F": float(F), "p": float(p), "y_differenced": dy, "x_differenced": dx,
            "n": len(pair)}


def _design(d: pd.DataFrame, cols: dict[str, int]) -> pd.DataFrame:
    return pd.concat({f"{c}_l{k}": d[c].shift(k) for c, k in cols.items()}, axis=1)


def _ols_r2(Xtr, ytr, Xte, yte, ridge: float = 0.0) -> tuple[float, float]:
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1
    Ztr, Zte = (Xtr - mu) / sd, (Xte - mu) / sd
    A = np.column_stack([np.ones(len(Ztr)), Ztr])
    reg = ridge * len(Ztr) * np.eye(A.shape[1])
    reg[0, 0] = 0   # don't shrink the intercept
    beta = (np.linalg.solve(A.T @ A + reg, A.T @ ytr) if ridge > 0
            else np.linalg.lstsq(A, ytr, rcond=None)[0])   # lstsq tolerates collinear columns
    r2 = lambda Z, y: 1 - ((y - np.column_stack([np.ones(len(Z)), Z]) @ beta) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return float(r2(Ztr, ytr)), float(r2(Zte, yte))


RIDGE = 1e-3   # mild, on standardized features; applied identically to AR and AR+X


def regression(d: pd.DataFrame, table: dict, dev_end) -> dict:
    X = _design(d, {f: max(v["best_lag"], 1) for f, v in table.items()})
    full = pd.concat([d["y"], X], axis=1).dropna()
    tr, te = full[full.index < dev_end], full[full.index >= dev_end]
    r2_in, r2_out = _ols_r2(tr.iloc[:, 1:].values, tr["y"].values, te.iloc[:, 1:].values, te["y"].values)
    return {"r2_dev": r2_in, "r2_test": r2_out, "lags": {f: max(v["best_lag"], 1) for f, v in table.items()}}


HORIZONS = (1, 6, 12, 24)


def incremental(d: pd.DataFrame, features: list[str], dev_end, h: int = 1, p: int = 24,
                future: str = "none", fc_map: dict[str, str] | None = None) -> dict:
    """
    Predict y(t+h) from information known at t: AR(p) on y vs AR(p) + X lags 0..23.
    No future weather is used. Out-of-sample R² on TEST.
    """
    y_in = d["y"].interpolate(limit=3, limit_area="inside")   # bridge ≤3h gaps in INPUT lags only
    ylags = pd.concat({f"y_l{k}": y_in.shift(k) for k in range(0, p)}, axis=1)
    ks = (0, 1, 2, 3, 6, 12, 23)
    xlags = {f"{f}_l{k}": d[f].shift(k) for f in features for k in ks}
    test_mask = d.index >= dev_end
    if future != "none":
        # future weather over (t, t+h] for forecastable features only.
        #   oracle   : actual future weather in fit and score (UPPER BOUND)
        #   forecast : real day-ahead ISSUED forecasts in fit and score. Fitting on actuals and
        #              scoring on forecasts breaks collinear coefficient cancellation, so both
        #              use forecasts; rows without an archived forecast (pre-2024) drop out.
        fks = sorted({-h, -max(h // 2, 1), -1})
        for f, col in (fc_map or {}).items():
            fut = d[col] if future == "forecast" else d[f]
            for k in fks:
                xlags[f"{f}_f{-k}"] = fut.shift(k)
    xlags = pd.concat(xlags, axis=1)
    target = d["y"].shift(-h).rename("y")
    full = pd.concat([target, ylags, xlags], axis=1).dropna()
    tr, te = full[full.index < dev_end], full[full.index >= dev_end]
    ycols, allcols = list(ylags.columns), list(ylags.columns) + list(xlags.columns)
    if len(tr) < 500 or len(te) < 200:
        return {"r2_test_ar": None, "r2_test_arx": None, "delta_r2": None, "mse_reduction": None,
                "n_train": len(tr), "n_test": len(te), "skipped": "too few complete rows"}
    _, r2_ar = _ols_r2(tr[ycols].values, tr["y"].values, te[ycols].values, te["y"].values, RIDGE)
    _, r2_arx = _ols_r2(tr[allcols].values, tr["y"].values, te[allcols].values, te["y"].values, RIDGE)
    # error-reduction is more readable than ΔR² when both are near 1
    mse = lambda r2: 1 - r2
    return {"r2_test_ar": r2_ar, "r2_test_arx": r2_arx, "delta_r2": r2_arx - r2_ar,
            "n_train": len(tr), "n_test": len(te),
            "mse_reduction": float(1 - mse(r2_arx) / mse(r2_ar)) if mse(r2_ar) > 0 else None}


def analyse(name: str) -> dict:
    df = load(name)
    features = [c for c in df.columns if c != "y" and not c.startswith("fc_")]
    dev_end = df.index[int(len(df) * DEV_FRAC)]
    views = {"raw": df, "anomaly": deseasonalise(df, dev_end)}
    out = {"idea": name, "dev_end": str(dev_end), "n_hours": len(df), "views": {}}
    for vname, d in views.items():
        dev = d[d.index < dev_end]
        table = lag_table(dev, features)
        out["views"][vname] = {
            "lags": table,
            "granger": {f: granger(dev, f) for f in features},
            "regression": regression(d, table, dev_end),
            "incremental": {h: incremental(d, features, dev_end, h) for h in HORIZONS},
            "forecastable": (fcm := forecastable(d, features, d.index >= dev_end)),
            "incremental_oracle": {h: incremental(d, features, dev_end, h, future="oracle", fc_map=fcm) for h in HORIZONS},
            "incremental_forecast": {h: incremental(d, features, dev_end, h, future="forecast", fc_map=fcm) for h in HORIZONS},
        }
    return out


def print_report(res: dict) -> None:
    print(f"\n{'=' * 100}\n{res['idea'].upper()}   (DEV ends {res['dev_end']})")
    for vname, v in res["views"].items():
        print(f"\n -- {vname}: Pearson r of X(t−k) vs Y(t)")
        print(f"   {'feature':24s}" + "".join(f"{('k=' + str(k)):>8s}" for k in SHOW_LAGS)
              + f"{'best k':>8s}{'r':>8s}{'ρ':>8s}{'p_eff':>10s}{'n_eff':>8s}{'Granger p':>11s}")
        for f, t in v["lags"].items():
            cells = "".join(f"{t['rows'][k]['pearson']:8.3f}" if t["rows"][k]["pearson"] is not None else f"{'—':>8s}"
                            for k in SHOW_LAGS)
            g = v["granger"][f]["p"]
            print(f"   {f:24s}{cells}{t['best_lag']:8d}{t['best_pearson']:8.3f}{t['best_spearman']:8.3f}"
                  f"{t['p_eff']:10.1e}{t['n_eff']:8.0f}{g:11.1e}")
        r = v["regression"]
        print(f"   OLS on best lags: R² dev {r['r2_dev']:.3f} | R² test {r['r2_test']:.3f}")
        fmt = lambda x, spec: format(x, spec) if x is not None else "n/a"
        for h, inc in v["incremental"].items():
            fo, ff = v["incremental_oracle"][h], v["incremental_forecast"][h]
            print(f"   {h:>2}h-ahead  R² test: y-history only {fmt(inc['r2_test_ar'], '.4f')} → + past weather "
                  f"{fmt(inc['r2_test_arx'], '.4f')}   (forecast error −{fmt(inc['mse_reduction'], '.1%')})"
                  f"\n{'':14s}real issued forecasts (fit on {ff['n_train']} h): y-history "
                  f"{fmt(ff['r2_test_ar'], '.4f')} → +X {fmt(ff['r2_test_arx'], '.4f')}"
                  f" (error −{fmt(ff['mse_reduction'], '.1%')})"
                  f"   | perfect-forecast upper bound {fmt(fo['r2_test_arx'], '.4f')}"
                  f" (−{fmt(fo['mse_reduction'], '.1%')})")
        print(f"   forecastable features: {list(v['forecastable'])}")


if __name__ == "__main__":
    (ROOT / "results").mkdir(exist_ok=True)
    for name in sys.argv[1:] or ["flood", "grid", "air"]:
        res = analyse(name)
        (ROOT / "results" / f"correlation_{name}.json").write_text(json.dumps(res, indent=1, default=str))
        print_report(res)

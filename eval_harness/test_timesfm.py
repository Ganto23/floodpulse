"""
Google TimesFM 2.5 zero-shot test (google/timesfm-2.5-200m-pytorch).

For each idea:
  * TEST period = last 20% of hours (same split as check_correlation.py)
  * rolling origins every 24 h through TEST; context = previous 1024 h; horizon = 24 h
  * models
      timesfm          zero-shot, target history only
      timesfm+xreg     TimesFM with in-context linear covariates = REAL issued day-ahead weather
                       forecasts (fc_* columns) over context + horizon. Real-time valid: only
                       forecasts that existed at the origin are used.
      drift            naive drift (last value + mean slope of the context)
      persistence      last value repeated
      seasonal_24      same hour yesterday
      seasonal_168     same hour last week
  * metrics: MAE, RMSE, MAPE (|actual| > 1% of mean), MAE at h = 1/6/12/24,
    80% interval coverage (TimesFM q10–q90). All models are scored on the same origins.

Run:  .venv/bin/python test_timesfm.py   → results/timesfm_<idea>.json
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).parent
CONTEXT, H, STEP, DEV_FRAC = 1024, 24, 24, 0.8
FC_MIN_COVERAGE = 0.95


def load_model():
    import timesfm
    import torch

    torch.set_float32_matmul_precision("high")
    m = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    m.compile(timesfm.ForecastConfig(max_context=CONTEXT, max_horizon=128, normalize_inputs=True,
                                     use_continuous_quantile_head=True, fix_quantile_crossing=True,
                                     return_backcast=True))
    return m


def fill(a: np.ndarray) -> np.ndarray:
    s = pd.Series(a).interpolate(limit_area="inside").ffill().bfill()
    return s.to_numpy(dtype=np.float32)


def metrics(pred: np.ndarray, act: np.ndarray) -> dict:
    m = ~np.isnan(act)
    e = pred[m] - act[m]
    scale = np.nanmean(np.abs(act))
    mm = m & (np.abs(act) > 0.01 * scale)
    by_h = {h: float(np.nanmean(np.abs(pred[:, h - 1] - act[:, h - 1]))) for h in (1, 6, 12, 24)}
    return {"mae": float(np.abs(e).mean()), "rmse": float(np.sqrt((e ** 2).mean())),
            "mape": float(np.mean(np.abs((pred[mm] - act[mm]) / act[mm]))), "mae_by_h": by_h}


def run(name: str, model) -> dict:
    df = pd.read_csv(ROOT / "data" / f"{name}.csv", index_col="time", parse_dates=True).astype(float)
    y = df["y"].to_numpy()
    fc_cols = [c for c in df.columns if c.startswith("fc_")]
    dev_end = int(len(df) * DEV_FRAC)
    origins = [o for o in range(dev_end, len(df) - H + 1, STEP)
               if o >= CONTEXT and np.isnan(y[o:o + H]).mean() <= 0.25
               and np.isnan(y[o - CONTEXT:o]).mean() <= 0.10]

    # covariate columns usable at every origin (archived forecasts exist over context+horizon)
    usable = [c for c in fc_cols if all(
        df[c].iloc[o - CONTEXT:o + H].notna().mean() >= FC_MIN_COVERAGE for o in origins)]

    ctx = [fill(y[o - CONTEXT:o]) for o in origins]
    act = np.stack([y[o:o + H] for o in origins])

    t0 = time.time()
    point, quant = model.forecast(horizon=H, inputs=ctx)
    # return_backcast=True (needed for covariates) prepends the reconstructed context:
    # the forecast is the LAST H steps.
    point, quant = np.asarray(point)[:, -H:], np.asarray(quant)[:, -H:, :]
    t_plain = time.time() - t0

    preds = {"timesfm": point}
    xreg_note = None
    if usable:
        try:
            t0 = time.time()
            cov = {c: [fill(df[c].to_numpy()[o - CONTEXT:o + H]) for o in origins] for c in usable}
            xp, _ = model.forecast_with_covariates(inputs=ctx, dynamic_numerical_covariates=cov,
                                                   xreg_mode="xreg + timesfm", ridge=1.0)
            preds["timesfm+xreg"] = np.stack([np.asarray(p)[-H:] for p in xp])
            xreg_note = f"{len(usable)} issued-forecast covariates: {usable} ({time.time() - t0:.1f}s)"
        except Exception as exc:
            xreg_note = f"covariate mode failed: {type(exc).__name__}: {exc}"[:300]
    else:
        xreg_note = "no issued-forecast covariates with full coverage"

    last = np.array([c[-1] for c in ctx])
    slope = np.array([(c[-1] - c[0]) / (len(c) - 1) for c in ctx])
    steps = np.arange(1, H + 1)
    preds["drift"] = last[:, None] + slope[:, None] * steps[None, :]
    preds["persistence"] = np.repeat(last[:, None], H, axis=1)
    preds["seasonal_24"] = np.stack([c[-24:] for c in ctx])
    preds["seasonal_168"] = np.stack([c[-168:-168 + H] for c in ctx])

    res = {m: metrics(p, act) for m, p in preds.items()}
    # EVENT windows: top 20% of origins by real rise above the last observed value (surges / spikes).
    # Selected on ACTUALS only, identically for every model.
    rise = np.nanmax(act, axis=1) - last
    ev = rise >= np.nanquantile(rise, 0.8)
    for m, p in preds.items():
        e = p[ev] - act[ev]
        peak_err = np.nanmax(p[ev], axis=1) - np.nanmax(act[ev], axis=1)
        res[m]["event"] = {"windows": int(ev.sum()), "mae": float(np.nanmean(np.abs(e))),
                           "peak_abs_err": float(np.nanmean(np.abs(peak_err))),
                           "peak_bias": float(np.nanmean(peak_err))}
    lo, hi = quant[..., 1], quant[..., -1]
    msk = ~np.isnan(act)
    res["timesfm"]["coverage_80"] = float(((act >= lo) & (act <= hi))[msk].mean())

    baselines = ["drift", "persistence", "seasonal_24", "seasonal_168"]
    best_base = min(baselines, key=lambda b: res[b]["mae"])
    skill = lambda m, b: 1 - res[m]["mae"] / res[b]["mae"]
    out = {
        "idea": name, "origins": len(origins), "context_h": CONTEXT, "horizon_h": H,
        "test_start": str(df.index[dev_end]), "seconds_timesfm": round(t_plain, 1),
        "xreg": xreg_note, "metrics": res, "best_baseline": best_base,
        "skill_mae": {m: {"vs_drift": skill(m, "drift"), "vs_best_baseline": skill(m, best_base)}
                      for m in preds if m.startswith("timesfm")},
    }
    return out


def show(r: dict) -> None:
    print(f"\n{'=' * 92}\n{r['idea'].upper()}  {r['origins']} rolling origins from {r['test_start'][:10]}, "
          f"context {r['context_h']} h, horizon {r['horizon_h']} h  (TimesFM {r['seconds_timesfm']}s)")
    print(f"   xreg: {r['xreg']}")
    print(f"   {'model':14s}{'MAE':>10s}{'RMSE':>10s}{'MAPE':>9s}{'MAE@1h':>10s}{'@6h':>9s}{'@12h':>9s}{'@24h':>9s}")
    for m, v in sorted(r["metrics"].items(), key=lambda kv: kv[1]["mae"]):
        b = v["mae_by_h"]
        print(f"   {m:14s}{v['mae']:10.4g}{v['rmse']:10.4g}{v['mape']:9.1%}"
              f"{b[1]:10.4g}{b[6]:9.4g}{b[12]:9.4g}{b[24]:9.4g}")
    print(f"   TimesFM 80% interval coverage: {r['metrics']['timesfm']['coverage_80']:.1%}")
    n_ev = r["metrics"]["timesfm"]["event"]["windows"]
    print(f"   EVENT windows (top-20% real rises, n={n_ev}):  MAE | peak |err| | peak bias")
    for m, v in sorted(r["metrics"].items(), key=lambda kv: kv[1]["event"]["mae"]):
        e = v["event"]
        print(f"      {m:14s}{e['mae']:10.4g}{e['peak_abs_err']:12.4g}{e['peak_bias']:+12.4g}")
    for m, s in r["skill_mae"].items():
        print(f"   {m}: MAE skill vs drift {s['vs_drift']:+.1%} | vs best baseline "
              f"({r['best_baseline']}) {s['vs_best_baseline']:+.1%}")


if __name__ == "__main__":
    (ROOT / "results").mkdir(exist_ok=True)
    model = load_model()
    for name in sys.argv[1:] or ["flood", "grid", "air"]:
        r = run(name, model)
        (ROOT / "results" / f"timesfm_{name}.json").write_text(json.dumps(r, indent=1, default=str))
        show(r)

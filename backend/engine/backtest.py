"""
Rolling-origin backtest for the nowcast regime.

At each origin o (spread over the back half of the history), everything is refit
on bins [0, o) only: the feature scaler, the Tucker decomposition, and the
forecaster on the latent temporal factors. Then we forecast bins [o, o+h) and
score against what really happened. Nothing after o reaches the model. Weather
and static OSM features are reindexed to the training bins, so no future
weather leaks in.

Scoring target: per-cell activity summed over the horizon window ("where will
activity be in the next 90 minutes"), which is the dispatch decision itself.

Models
  urbanpulse   Tucker denoise -> zero-shot forecast of latent U_t -> projection
  no_denoise   same forecaster applied directly to each cell's raw log1p series (ablation)
  persistence  last h bins repeated
  hist_mean    per-cell mean rate over training window × h
  seasonal     same window one day earlier (when ≥ 1 day of history)
  zero         predict nothing anywhere: the sparsity floor (WAPE = 1 exactly)

Origins whose horizon window holds < MIN_WINDOW_EVENTS real sightings are scanner
gaps (collection outages, not quiet streets); they're excluded and counted.

Metrics
  wape         POOLED over origins: Σ|pred−actual| / Σactual. < 1 beats "zero".
  mae, rmse    per-cell horizon totals
  spearman     rank correlation of cells (does it rank places correctly?)
  precision_k  share of the predicted top-K cells that land in the actual top-K
  share_err    total-variation distance between predicted and actual activity *shares*
               (0 = perfect allocation, 1 = disjoint). Independent of scan volume.
  volume_err   |Σpred − Σactual| / Σactual (city-wide volume, sensitive to scan effort)
  (mae/rmse/spearman/precision_k/share_err/volume_err are means over valid origins)
"""

from __future__ import annotations

import logging
import time

import numpy as np
from scipy.stats import spearmanr

from engine.forecast_engine import ForecastEngine
from engine.tensor_engine import TensorEngine, freq_hours

log = logging.getLogger(__name__)

MODELS = ("urbanpulse", "no_denoise", "persistence", "hist_mean", "seasonal", "zero")
MIN_WINDOW_EVENTS = 20
MODEL_LABELS = {
    "urbanpulse": "UrbanPulse (Tucker + zero-shot)",
    "no_denoise": "Same forecaster, no denoising",
    "persistence": "Persistence (last window)",
    "hist_mean": "Historical mean",
    "seasonal": "Seasonal naive (t − 24h)",
    "zero": "Predict zero (sparsity floor)",
}


def _metrics(pred: np.ndarray, actual: np.ndarray, k: int) -> dict[str, float]:
    err = pred - actual
    tot = actual.sum()
    ps = pred.sum()
    share_err = 0.5 * float(np.abs(pred / ps - actual / tot).sum()) if ps > 0 and tot > 0 else 1.0
    out = {
        "abs_err": float(np.abs(err).sum()), "actual": float(tot),
        "share_err": share_err,
        "mae": float(np.abs(err).mean()),
        "rmse": float(np.sqrt((err ** 2).mean())),
        "volume_err": float(abs(pred.sum() - tot) / tot) if tot > 0 else np.nan,
    }
    if actual.std() > 0 and pred.std() > 0:
        out["spearman"] = float(spearmanr(pred, actual).statistic)
    else:
        out["spearman"] = np.nan
    if tot > 0 and pred.std() > 0:   # a constant forecast ranks nothing
        kth = np.sort(actual)[-k]
        actual_top = set(np.where((actual >= max(kth, 1e-12)) & (actual > 0))[0])
        pred_top = set(np.argsort(-pred, kind="stable")[:k])
        out["precision_k"] = len(pred_top & actual_top) / k
    else:
        out["precision_k"] = np.nan
    return out


def run_backtest(*, events, cells, freq, highlight_category, weather, static, realized, times,
                 horizon: int, forecaster: ForecastEngine, tensor_engine: TensorEngine,
                 n_origins: int = 24, min_train_frac: float = 0.5, top_k: int | None = None) -> dict:
    t0 = time.time()
    T, S = len(times), len(cells)
    k = top_k or max(10, S // 40)
    day = int(round(24 / freq_hours(freq)))
    first, last = max(int(T * min_train_frac), 2 * horizon), T - horizon
    if last <= first:
        raise ValueError(f"history too short for backtest ({T} bins, horizon {horizon})")
    origins = np.unique(np.linspace(first, last, n_origins).astype(int))

    per_origin = []
    for o in origins:
        actual_bins = realized[:, o:o + horizon]
        actual = actual_bins.sum(axis=1)
        if actual.sum() < MIN_WINDOW_EVENTS:
            per_origin.append({"origin": times[o].isoformat(), "actual_total": float(actual.sum()),
                               "active_cells": int((actual > 0).sum()), "excluded": "scanner_gap",
                               "models": {}})
            continue
        train = realized[:, :o]
        preds: dict[str, np.ndarray] = {}

        tens = tensor_engine.build(events, cells, freq, highlight_category, weather, static,
                                   times=times[:o])
        fc = forecaster.forecast(tens.temporal_factors.T, horizon)
        preds["urbanpulse"] = tens.project(fc.point.T).sum(axis=1)

        raw_fc = forecaster.forecast(np.log1p(train), horizon)
        preds["no_denoise"] = np.clip(np.expm1(raw_fc.point), 0, None).sum(axis=1)

        preds["persistence"] = train[:, -horizon:].sum(axis=1)
        preds["hist_mean"] = train.mean(axis=1) * horizon
        if o - day >= 0:
            preds["seasonal"] = realized[:, o - day:o - day + horizon].sum(axis=1)
        preds["zero"] = np.zeros(S)

        per_origin.append({
            "origin": times[o].isoformat(),
            "actual_total": float(actual.sum()),
            "active_cells": int((actual > 0).sum()),
            "excluded": None,
            "models": {m: _metrics(p, actual, k) for m, p in preds.items()},
        })

    summary = {}
    for m in MODELS:
        rows = [po["models"][m] for po in per_origin if m in po["models"]]
        if not rows:
            continue
        summary[m] = {key: _nanmean([r[key] for r in rows]) for key in rows[0]
                      if key not in ("abs_err", "actual")}
        summary[m]["wape"] = sum(r["abs_err"] for r in rows) / sum(r["actual"] for r in rows)
        summary[m]["origins"] = len(rows)

    def skill(metric: str, ref: str) -> float | None:
        a, b = summary["urbanpulse"].get(metric), summary.get(ref, {}).get(metric)
        if a is None or b is None or not np.isfinite(a) or not np.isfinite(b) or b == 0:
            return None
        return float(1 - a / b)

    elapsed = time.time() - t0
    log.info("backtest: %d origins in %.1fs", len(origins), elapsed)
    return {
        "freq": freq, "horizon_steps": horizon,
        "horizon_minutes": round(horizon * freq_hours(freq) * 60),
        "top_k": k, "cells": S, "origins": int(sum(1 for po in per_origin if not po["excluded"])),
        "window": [times[origins[0]].isoformat(), times[origins[-1] + horizon - 1].isoformat()],
        "forecaster": forecaster.describe()["backend"],
        "labels": MODEL_LABELS,
        "summary": summary,
        "skill": {
            "wape_vs_persistence": skill("wape", "persistence"),
            "wape_vs_hist_mean": skill("wape", "hist_mean"),
            "wape_vs_no_denoise": skill("wape", "no_denoise"),
                "wape_vs_seasonal": skill("wape", "seasonal"),
            "wape_vs_zero": skill("wape", "zero"),
            "share_vs_persistence": skill("share_err", "persistence"),
            "share_vs_hist_mean": skill("share_err", "hist_mean"),
            "share_vs_no_denoise": skill("share_err", "no_denoise"),
            "share_vs_seasonal": skill("share_err", "seasonal"),
        },
        "excluded_origins": sum(1 for po in per_origin if po["excluded"]),
        "min_window_events": MIN_WINDOW_EVENTS,
        "per_origin": per_origin,
        "elapsed_s": round(elapsed, 1),
    }


def _nanmean(xs: list[float]) -> float | None:
    arr = np.array(xs, dtype=float)
    return float(np.nanmean(arr)) if np.isfinite(arr).any() else None

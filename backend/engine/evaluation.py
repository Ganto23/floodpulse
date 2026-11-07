"""
Pre-registered correlation study (dev → holdout).

Protocol, fixed before results were seen:
  * HOLDOUT = the final HOLDOUT_HOURS of the stream. Nothing in it is used to choose anything.
  * DEV     = everything before. Scale selection happens here only.
  * Candidate scales are business-motivated, not a free grid search:
        H3 res 9 (~0.1 km², block level), 8 (~0.7 km², neighbourhood), 7 (~5 km², courier zone)
      × decision window 90 min (dispatch), 3 h (shift block), 6 h (half-day shift)
    Each window is forecast as 6 steps (bin = window / 6).
  * Selection criterion (declared): highest mean out-of-sample Pearson correlation of
    log1p(UrbanPulse forecast) vs log1p(actual) over dev origins. Ties at zero are why
    Pearson-on-log1p is used instead of Spearman over all cells.
  * Spearman is computed only over cells with activity in the TRAINING period. Conditioning
    on "active in either period" would select on the outcome and manufacture a negative
    correlation (Berkson's paradox).
  * Then the HOLDOUT is scored once, at the selected scale, with three tests:
      A. forecast skill: UrbanPulse vs no-denoise ablation, persistence, historical mean
      B. spatial persistence: per-cell activity rate in DEV vs in HOLDOUT
      C. alt-data cross-section: OSM transit / pedestrian / building density vs activity,
         fitted on DEV cells, scored on HOLDOUT, restricted to cells that OSM actually covers

Windows with < MIN_WINDOW_EVENTS sightings are scanner outages; they're excluded and counted.
"""

from __future__ import annotations

import logging
import time

import h3
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from config import MAX_CELLS
from data import h3_grid
from engine.forecast_engine import ForecastEngine
from engine.tensor_engine import TensorEngine, floor_ts

log = logging.getLogger(__name__)

HOLDOUT_HOURS = 48
RESOLUTIONS = (9, 8, 7)
WINDOWS_MIN = (90, 180, 360)
STEPS = 6
MIN_WINDOW_EVENTS = 20
DEV_MIN_TRAIN_HOURS = 24
MAX_DEV_ORIGINS = 16
SCALE_LABEL = {9: "block (~0.1 km²)", 8: "neighbourhood (~0.7 km²)", 7: "courier zone (~5 km²)"}
OSM_FEATURES = ("transit_proximity", "pedestrian_m", "buildings")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _corr(fn, x, y) -> float | None:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return None
    return float(fn(x, y).statistic)


def _realized(ev: pd.DataFrame, cells: list[str], times: pd.DatetimeIndex, freq: str) -> np.ndarray:
    b = ev.assign(bin=floor_ts(ev["timestamp"], freq))
    b = b[b["bin"].isin(times) & b["h3"].isin(cells)]
    return (b.pivot_table(index="h3", columns="bin", values="value", aggfunc="sum")
            .reindex(index=pd.Index(cells), columns=times, fill_value=0).fillna(0).to_numpy())


def _window_metrics(pred: np.ndarray, actual: np.ndarray, seen: np.ndarray) -> dict:
    """`seen` = cells with any training-period activity (outcome-independent)."""
    return {
        "pearson_log": _corr(pearsonr, np.log1p(np.clip(pred, 0, None)), np.log1p(actual)),
        "spearman_active": _corr(spearmanr, pred[seen], actual[seen]),
        "abs_err": float(np.abs(pred - actual).sum()), "actual": float(actual.sum()),
    }


def _summarise(rows: list[dict]) -> dict:
    out = {}
    for m in rows[0]["models"] if rows else []:
        ms = [r["models"][m] for r in rows]
        mean = lambda k: (float(np.mean(v)) if (v := [x[k] for x in ms if x[k] is not None]) else None)
        out[m] = {"pearson_log": mean("pearson_log"), "spearman_active": mean("spearman_active"),
                  "wape": sum(x["abs_err"] for x in ms) / max(sum(x["actual"] for x in ms), 1e-9),
                  "windows": len(ms)}
    return out


class _Scale:
    """Everything needed to forecast at one (resolution, window) scale."""

    def __init__(self, events, res, window_min, infra, weather, t_end):
        self.res, self.window_min = res, window_min
        self.freq = f"{window_min // STEPS}min"
        self.ev = events.assign(h3=[h3.latlng_to_cell(a, b, res)
                                    for a, b in zip(events["latitude"], events["longitude"])])
        self.cells = self.ev["h3"].value_counts().index[:MAX_CELLS].tolist()
        self.static = np.column_stack([
            h3_grid.cell_counts(infra.transit, self.cells, res, smooth_k=1),
            h3_grid.cell_counts(infra.footways, self.cells, res, weight="length_m"),
            h3_grid.cell_counts(infra.buildings, self.cells, res),
        ])
        start = floor_ts(events["timestamp"], self.freq).min()
        self.times = pd.date_range(start, floor_ts(pd.Series([t_end]), self.freq).iloc[0], freq=self.freq)
        self.R = _realized(self.ev, self.cells, self.times, self.freq)
        self.weather = weather

    def origins(self, t_from, t_to, min_train_bins: int) -> list[int]:
        """Non-overlapping window starts o with [o, o+STEPS) inside [t_from, t_to)."""
        idx = [i for i, t in enumerate(self.times) if t >= t_from and i >= min_train_bins]
        out, i = [], idx[0] if idx else len(self.times)
        while i + STEPS <= len(self.times) and self.times[i + STEPS - 1] < t_to:
            out.append(i)
            i += STEPS
        return out

    def score_window(self, o, hl_cat, te: TensorEngine, fe: ForecastEngine) -> dict | None:
        actual = self.R[:, o:o + STEPS].sum(1)
        if actual.sum() < MIN_WINDOW_EVENTS:
            return None
        train = self.R[:, :o]
        tens = te.build(self.ev, self.cells, self.freq, hl_cat, self.weather, self.static,
                        times=self.times[:o])
        up = tens.project(fe.forecast(tens.temporal_factors.T, STEPS).point.T).sum(1)
        nd = np.clip(np.expm1(fe.forecast(np.log1p(train), STEPS).point), 0, None).sum(1)
        recent = train[:, -STEPS:].sum(1)
        preds = {"urbanpulse": up, "no_denoise": nd, "persistence": recent,
                 "hist_mean": train.mean(1) * STEPS}
        return {"origin": self.times[o].isoformat(),
                "models": {m: _window_metrics(p, actual, train.sum(1) > 0) for m, p in preds.items()}}


# --------------------------------------------------------------------------- #
def run_study(*, events, infra, weather, highlight_category, forecaster: ForecastEngine,
              tensor_engine: TensorEngine) -> dict:
    t0 = time.time()
    t_end = events["timestamp"].max()
    t_hold = t_end - pd.Timedelta(hours=HOLDOUT_HOURS)
    t_start = events["timestamp"].min()

    # ---------------- DEV: choose scale ---------------------------------
    dev_grid, scales = [], {}
    for res in RESOLUTIONS:
        for w in WINDOWS_MIN:
            sc = _Scale(events, res, w, infra, weather, t_end)
            scales[(res, w)] = sc
            min_train = int(DEV_MIN_TRAIN_HOURS * 60 / (w // STEPS))
            origins = sc.origins(t_start, t_hold, min_train)
            if len(origins) > MAX_DEV_ORIGINS:
                origins = [origins[i] for i in np.linspace(0, len(origins) - 1, MAX_DEV_ORIGINS).astype(int)]
            rows = [r for o in origins if (r := sc.score_window(o, highlight_category, tensor_engine, forecaster))]
            summ = _summarise(rows)
            dev_grid.append({"res": res, "window_min": w, "freq": sc.freq, "cells": len(sc.cells),
                             "label": SCALE_LABEL[res], "windows": len(rows),
                             "excluded": len(origins) - len(rows), "summary": summ})
    eligible = [g for g in dev_grid if g["summary"].get("urbanpulse", {}).get("pearson_log") is not None]
    chosen = max(eligible, key=lambda g: g["summary"]["urbanpulse"]["pearson_log"])
    sc = scales[(chosen["res"], chosen["window_min"])]

    # ---------------- HOLDOUT A: forecast skill -------------------------
    h_origins = sc.origins(t_hold, t_end + pd.Timedelta(minutes=1), 0)
    h_rows = [r for o in h_origins if (r := sc.score_window(o, highlight_category, tensor_engine, forecaster))]
    holdout_forecast = {"windows": len(h_rows), "excluded": len(h_origins) - len(h_rows),
                        "summary": _summarise(h_rows), "per_window": h_rows}

    # ---------------- HOLDOUT B: spatial persistence --------------------
    dev_mask = sc.times < t_hold
    dev_hours = dev_mask.sum() * sc.window_min / STEPS / 60
    hold_hours = (~dev_mask).sum() * sc.window_min / STEPS / 60
    dev_rate = sc.R[:, dev_mask].sum(1) / dev_hours
    hold_rate = sc.R[:, ~dev_mask].sum(1) / hold_hours
    active = dev_rate > 0   # condition on the past only
    spatial = {
        "cells": int(len(sc.cells)), "active_cells": int(active.sum()),
        "pearson_log": _corr(pearsonr, np.log1p(dev_rate), np.log1p(hold_rate)),
        "spearman_active": _corr(spearmanr, dev_rate[active], hold_rate[active]),
        "top_decile_retention": _top_retention(dev_rate, hold_rate, 0.1),
        "dev_hours": round(float(dev_hours), 1), "holdout_hours": round(float(hold_hours), 1),
    }

    # ---------------- HOLDOUT C: OSM cross-section ----------------------
    osm = _osm_cross_section(sc, infra, dev_rate, hold_rate)

    return {
        "protocol": {
            "holdout_hours": HOLDOUT_HOURS, "holdout_start": t_hold.isoformat(), "end": t_end.isoformat(),
            "selection_metric": "dev mean Pearson(log1p forecast, log1p actual), UrbanPulse",
            "candidates": [f"res {r} × {w} min" for r in RESOLUTIONS for w in WINDOWS_MIN],
            "min_window_events": MIN_WINDOW_EVENTS, "forecaster": forecaster.describe()["backend"],
        },
        "dev_grid": dev_grid,
        "selected": {"res": chosen["res"], "window_min": chosen["window_min"], "freq": chosen["freq"],
                     "label": chosen["label"], "cells": chosen["cells"]},
        "holdout": {"forecast": holdout_forecast, "spatial_persistence": spatial, "osm": osm},
        "elapsed_s": round(time.time() - t0, 1),
    }


def _top_retention(a: np.ndarray, b: np.ndarray, frac: float) -> float | None:
    k = max(1, int(round(len(a) * frac)))
    if a.sum() == 0 or b.sum() == 0:
        return None
    return len(set(np.argsort(-a)[:k]) & set(np.argsort(-b)[:k])) / k


def _osm_cross_section(sc: _Scale, infra, dev_rate, hold_rate) -> dict:
    if infra is None or infra.node_count == 0:
        return {"available": False, "reason": "no OSM infrastructure loaded"}
    # a cell is covered only if its whole boundary sits inside successfully-loaded OSM tiles
    covered = np.array([all(infra.covers(la, lo) for la, lo in h3.cell_to_boundary(c))
                        for c in sc.cells])
    if covered.sum() < 10:
        return {"available": False, "reason": f"only {int(covered.sum())} cells inside OSM coverage"}
    X = np.log1p(sc.static[covered])
    y_dev, y_hold = np.log1p(dev_rate[covered]), np.log1p(hold_rate[covered])

    per_feature = {f: {"pearson_dev": _corr(pearsonr, X[:, j], y_dev),
                       "pearson_holdout": _corr(pearsonr, X[:, j], y_hold)}
                   for j, f in enumerate(OSM_FEATURES)}
    A = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(A, y_dev, rcond=None)
    fit_dev, pred_hold = A @ beta, A @ beta
    r2 = lambda y, yh: float(1 - ((y - yh) ** 2).sum() / ((y - y.mean()) ** 2).sum()) if y.std() > 0 else None

    # spatial-block CV on DEV: leave out one parent block at a time (guards against autocorrelation)
    parent_res = max(sc.res - 2, 0)
    blocks = np.array([h3.cell_to_parent(c, parent_res) for c in np.array(sc.cells)[covered]])
    cv_pred = np.zeros(len(y_dev))
    for blk in np.unique(blocks):
        m = blocks == blk
        if (~m).sum() < 5:
            cv_pred[m] = y_dev[~m].mean() if (~m).any() else y_dev.mean()
            continue
        b, *_ = np.linalg.lstsq(A[~m], y_dev[~m], rcond=None)
        cv_pred[m] = A[m] @ b
    return {
        "available": True, "covered_cells": int(covered.sum()), "total_cells": int(len(sc.cells)),
        "per_feature": per_feature,
        "ols": {
            "features": list(OSM_FEATURES), "coef": [round(float(x), 4) for x in beta],
            "r2_dev_in_sample": r2(y_dev, fit_dev),
            "r2_dev_spatial_block_cv": r2(y_dev, cv_pred), "cv_blocks": int(len(np.unique(blocks))),
            "r2_holdout": r2(y_hold, pred_hold),
            "pearson_holdout": _corr(pearsonr, pred_hold, y_hold),
        },
    }

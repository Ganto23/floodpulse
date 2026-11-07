"""
Tensor decomposition engine.

Builds X ∈ R^{S × T × F}  (H3 cells × time bins × feature metrics)

    F = [activity, highlight (lures), precipitation, temperature, wind,
         transit proximity, pedestrian network density, building density]

then fits a low-rank Tucker model X ≈ G ×₁ U_s ×₂ U_t ×₃ U_f via TensorLy.
The low-rank reconstruction is the denoised signal; U_t (T × R_t) are the latent
temporal "urban growth" vectors handed to the forecaster, and new temporal rows
are projected back through G, U_s, U_f to obtain per-cell forecasts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import tensorly as tl
from tensorly.decomposition import tucker

from config import (MAX_TIME_STEPS, MIN_BIN_DENSITY, TUCKER_RANK_FEATURE,
                    TUCKER_RANK_SPATIAL, TUCKER_RANK_TEMPORAL)

log = logging.getLogger(__name__)
tl.set_backend("numpy")

FEATURES = ("activity", "highlight", "precipitation", "temperature", "wind_speed",
            "transit_proximity", "pedestrian_density", "building_density")
FREQ_LADDER = ("15min", "30min", "1h", "3h", "6h", "1D", "1W", "MS")


def freq_hours(freq: str) -> float:
    if freq == "MS":
        return 730.5
    return pd.Timedelta(pd.tseries.frequencies.to_offset(freq)).total_seconds() / 3600


def select_frequency(ts: pd.Series, preferred: str, max_steps: int = MAX_TIME_STEPS,
                     min_density: float = MIN_BIN_DENSITY) -> tuple[str, list[str]]:
    """
    Start at the mode's preferred bin and coarsen until at least `min_density`
    of the most-recent `max_steps` bins contain an event — avoids feeding an
    all-zeros tensor to the decomposition when the real stream is sparse.
    """
    notes: list[str] = []
    start = FREQ_LADDER.index(preferred) if preferred in FREQ_LADDER else 0
    for freq in FREQ_LADDER[start:]:
        bins = floor_ts(ts, freq)
        last = bins.max()
        rng = time_index(bins.min(), last, freq)[-max_steps:]
        density = bins[bins >= rng[0]].nunique() / max(len(rng), 1)
        if density >= min_density and len(rng) >= 8:
            if freq != preferred:
                notes.append(f"stream too sparse at {preferred}; coarsened to {freq} (bin density {density:.0%})")
            return freq, notes
    notes.append("stream sparse at every resolution; using monthly bins")
    return "MS", notes


def time_index(start, end, freq: str) -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq=freq)


def floor_ts(ts: pd.Series, freq: str) -> pd.Series:
    if freq == "MS":
        return ts.dt.tz_convert("UTC").dt.tz_localize(None).dt.to_period("M").dt.to_timestamp().dt.tz_localize("UTC")
    return ts.dt.floor(freq)


@dataclass
class Scaler:
    mean: np.ndarray
    std: np.ndarray

    def fwd(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / self.std

    def inv(self, z: np.ndarray) -> np.ndarray:
        return z * self.std + self.mean


@dataclass
class TensorResult:
    freq: str
    cells: list[str]
    times: pd.DatetimeIndex
    X: np.ndarray                 # standardized S×T×F
    X_hat: np.ndarray             # Tucker reconstruction S×T×F
    core: np.ndarray
    factors: list[np.ndarray]     # [U_s, U_t, U_f]
    scaler: Scaler
    realized: np.ndarray          # S×T activity in source units (sum of `value`)
    highlight: np.ndarray         # S×T highlight-category counts
    rel_error: float
    ranks: tuple[int, int, int]
    notes: list[str] = field(default_factory=list)

    @property
    def temporal_factors(self) -> np.ndarray:
        return self.factors[1]

    def activity_from_z(self, z_activity: np.ndarray) -> np.ndarray:
        """Inverse-transform the activity slice (z-space, log1p) to source units."""
        log_act = z_activity * self.scaler.std[0] + self.scaler.mean[0]
        return np.clip(np.expm1(log_act), 0, None)

    @property
    def denoised(self) -> np.ndarray:
        return self.activity_from_z(self.X_hat[:, :, 0])

    def project(self, temporal_rows: np.ndarray) -> np.ndarray:
        """Reconstruct activity (S × h) for new latent temporal rows (h × R_t)."""
        U_s, _, U_f = self.factors
        Z = tl.tucker_to_tensor((self.core, [U_s, temporal_rows, U_f]))
        return self.activity_from_z(Z[:, :, 0])

    def explained_variance(self) -> list[float]:
        """Share of core energy carried by each temporal latent component."""
        energy = np.square(self.core).sum(axis=(0, 2))
        return (energy / energy.sum()).round(4).tolist() if energy.sum() else []


class TensorEngine:
    def __init__(self, ranks: tuple[int, int, int] = (TUCKER_RANK_SPATIAL, TUCKER_RANK_TEMPORAL,
                                                      TUCKER_RANK_FEATURE)) -> None:
        self.ranks = ranks

    def build(
        self,
        events: pd.DataFrame,                 # standardized + `h3`
        cells: list[str],
        freq: str,
        highlight_category: str,
        weather: pd.DataFrame | None,
        static_features: np.ndarray,          # S × 3 (transit, pedestrian, building)
        times: pd.DatetimeIndex | None = None,
        max_steps: int = MAX_TIME_STEPS,
    ) -> TensorResult:
        notes: list[str] = []
        ev = events.assign(bin=floor_ts(events["timestamp"], freq))
        if times is None:
            times = time_index(ev["bin"].min(), ev["bin"].max(), freq)[-max_steps:]
        ev = ev[ev["bin"].isin(times) & ev["h3"].isin(cells)]

        S, T, F = len(cells), len(times), len(FEATURES)
        cell_ix = pd.Index(cells)
        realized = (ev.pivot_table(index="h3", columns="bin", values="value", aggfunc="sum")
                    .reindex(index=cell_ix, columns=times, fill_value=0).fillna(0).to_numpy())
        hl = ev[ev["category"] == highlight_category]
        highlight = (hl.pivot_table(index="h3", columns="bin", values="value", aggfunc="count")
                     .reindex(index=cell_ix, columns=times, fill_value=0).fillna(0).to_numpy()
                     if not hl.empty else np.zeros((S, T)))

        raw = np.zeros((S, T, F))
        raw[:, :, 0] = np.log1p(np.clip(realized, 0, None))
        raw[:, :, 1] = np.log1p(highlight)

        weather_mask = np.zeros(T, dtype=bool)
        if weather is not None and not weather.empty:
            w = self._align_weather(weather, times, freq)
            weather_mask = w.notna().all(axis=1).to_numpy()
            for j, col in enumerate(("precipitation", "temperature", "wind_speed"), start=2):
                raw[:, :, j] = w[col].to_numpy()[None, :]
            if (~weather_mask).any():
                notes.append(f"{int((~weather_mask).sum())}/{T} bins lack archive weather (neutral-filled)")
        else:
            notes.append("no weather available; weather features neutral")

        raw[:, :, 5:8] = np.log1p(static_features)[:, None, :]

        # standardize per feature, using only observed weather bins for weather stats
        mean, std = np.zeros(F), np.ones(F)
        for f in range(F):
            vals = raw[:, weather_mask, f] if 2 <= f <= 4 else raw[:, :, f]
            vals = vals[np.isfinite(vals)]
            if vals.size:
                mean[f] = vals.mean()
                std[f] = vals.std() or 1.0
        scaler = Scaler(mean, std)
        X = scaler.fwd(raw)
        X[:, ~weather_mask, 2:5] = 0.0        # missing weather = neutral (mean)
        X = np.nan_to_num(X)

        ranks = (min(self.ranks[0], S), min(self.ranks[1], T), min(self.ranks[2], F))
        core, factors = tucker(X, rank=list(ranks), init="svd", n_iter_max=200, tol=1e-6,
                               random_state=0)
        X_hat = tl.tucker_to_tensor((core, factors))
        act_err = np.linalg.norm(X[:, :, 0] - X_hat[:, :, 0]) / (np.linalg.norm(X[:, :, 0]) or 1.0)

        log.info("tucker %s on %s: activity rel. error %.3f", ranks, X.shape, act_err)
        return TensorResult(freq=freq, cells=cells, times=times, X=X, X_hat=X_hat, core=core,
                            factors=list(factors), scaler=scaler, realized=realized,
                            highlight=highlight, rel_error=float(act_err), ranks=ranks, notes=notes)

    @staticmethod
    def _align_weather(weather: pd.DataFrame, times: pd.DatetimeIndex, freq: str) -> pd.DataFrame:
        w = weather.sort_index()
        w_step = w.index.to_series().diff().median() if len(w) > 1 else pd.Timedelta(hours=1)
        b_step = pd.Timedelta(hours=freq_hours(freq))
        if w_step > b_step:
            # source coarser than bins (hourly weather, 15-min bins): carry each reading
            # forward across its own interval and split precipitation totals evenly
            out = w.reindex(times, method="ffill", tolerance=w_step)
            out["precipitation"] = out["precipitation"] * (b_step / w_step)
            return out
        w = w.copy()
        w.index = floor_ts(w.index.to_series(), freq).to_numpy()
        agg = w.groupby(level=0).agg({"precipitation": "sum", "temperature": "mean", "wind_speed": "mean"})
        return agg.reindex(times)

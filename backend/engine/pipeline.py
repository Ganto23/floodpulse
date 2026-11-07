"""
End-to-end orchestration:

  loader → focus region → H3 bin → OSM infra + Open-Meteo weather
        → Tucker tensor (short regime @ 15-min-ish, long regime @ monthly)
        → zero-shot forecast of latent temporal factors → projected per-cell surfaces
        → frame store queried by the API.
"""

from __future__ import annotations

import bisect
import logging
import math
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone

import h3
import numpy as np
import pandas as pd

import config
from data import h3_grid
from engine import signals
from engine.backtest import run_backtest
from engine.evaluation import run_study
from engine.forecast_engine import ForecastEngine
from engine.tensor_engine import TensorEngine, TensorResult, freq_hours, select_frequency, time_index
from loaders import get_loader
from loaders.osm_loader import OSMInfrastructure, OSMInfrastructureLoader
from loaders.weather_loader import OpenMeteoWeatherLoader, WeatherResult

log = logging.getLogger(__name__)


@dataclass
class Regime:
    name: str                       # "nowcast" | "longrange"
    tensor: TensorResult
    horizon_times: pd.DatetimeIndex
    forecast: np.ndarray            # S × h
    lo: np.ndarray
    hi: np.ndarray
    momentum: np.ndarray            # S × (T + h)
    weather: WeatherResult


@dataclass
class FrameRef:
    ts: pd.Timestamp
    regime: Regime
    idx: int                        # index into the regime's T + h axis
    kind: str                       # "historical" | "forecast"


@dataclass
class PipelineState:
    status: str = "idle"            # idle | loading | ready | error
    stage: str = ""
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    loader: dict = field(default_factory=dict)
    events: pd.DataFrame | None = None
    cells: list[str] = field(default_factory=list)
    centers: list[tuple[float, float]] = field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None
    infra: OSMInfrastructure | None = None
    regimes: dict[str, Regime] = field(default_factory=dict)
    frames: list[FrameRef] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    static: np.ndarray | None = None
    backtest_status: str = "pending"  # pending | running | ready | error
    backtest: dict | None = None
    backtest_error: str | None = None
    study_status: str = "pending"
    study: dict | None = None
    study_error: str | None = None


class UrbanPulsePipeline:
    def __init__(self) -> None:
        self.profile = config.active_profile()
        self.state = PipelineState()
        self.forecaster = ForecastEngine()
        self.tensor_engine = TensorEngine()
        self._lock = threading.Lock()
        self._frame_ts: list[pd.Timestamp] = []
        self.highlight_category = self.profile.highlight_category
        self.highlight_label = self.profile.highlight_label
        self.value_label = self.profile.value_label
        self.event_noun = self.profile.event_noun

    # ------------------------------------------------------------------ #
    def start_background(self) -> None:
        threading.Thread(target=self.run, name="urbanpulse-pipeline", daemon=True).start()

    def run(self) -> None:
        if not self._lock.acquire(blocking=False):
            return
        st = self.state = PipelineState(status="loading", started_at=time.time())
        try:
            self._run(st)
            st.status, st.stage = "ready", "ready"
        except Exception as exc:
            log.exception("pipeline failed")
            st.status, st.error = "error", f"{type(exc).__name__}: {exc}"
            st.notes.append(traceback.format_exc(limit=3))
        finally:
            st.finished_at = time.time()
        if st.status == "ready":   # map is live; backtest runs after, off the critical path
            self._run_backtest(st)
            self._run_study(st)
            self._lock.release()

    def _run(self, st: PipelineState) -> None:
        st.stage = "ingesting telemetry"
        loader = get_loader(config.DATASET_MODE)
        events = loader.load_data()
        st.loader = loader.describe()
        self.highlight_category = loader.highlight_category or self.profile.highlight_category
        self.highlight_label = loader.highlight_label or self.profile.highlight_label
        self.value_label = loader.value_label or self.profile.value_label
        self.event_noun = loader.event_noun or self.profile.event_noun

        st.stage = "indexing H3 grid"
        events = self._focus(events, st)
        events = h3_grid.index_events(events, config.H3_RESOLUTION)
        counts = events["h3"].value_counts()
        st.cells = counts.index[: config.MAX_CELLS].tolist()
        if len(counts) > config.MAX_CELLS:
            st.notes.append(f"kept {config.MAX_CELLS} busiest of {len(counts)} H3 cells")
        st.centers = [h3_grid.cell_center(c) for c in st.cells]
        st.events = events
        st.bbox = h3_grid.bbox_of(events)

        st.stage = "loading OSM infrastructure"
        st.infra = OSMInfrastructureLoader(st.bbox).load()
        static = np.column_stack([
            h3_grid.cell_counts(st.infra.transit, st.cells, smooth_k=1),
            h3_grid.cell_counts(st.infra.footways, st.cells, weight="length_m"),
            h3_grid.cell_counts(st.infra.buildings, st.cells),
        ])
        st.static = static

        weather_loader = OpenMeteoWeatherLoader(st.bbox)

        # -------- short-horizon nowcast regime ------------------------------
        st.stage = "decomposing nowcast tensor"
        freq, notes = select_frequency(events["timestamp"], self.profile.preferred_freq)
        st.notes.extend(notes)
        times = time_index(*_floor_range(events["timestamp"], freq), freq)[-config.MAX_TIME_STEPS:]
        wx = weather_loader.load(times[0], times[-1] + pd.Timedelta(hours=freq_hours(freq)))
        tens = self.tensor_engine.build(events, st.cells, freq, self.highlight_category,
                                        wx.frame, static, times=times)
        horizon = max(4, math.ceil(self.profile.short_horizon_minutes / 60 / freq_hours(freq)))
        st.stage = "forecasting nowcast (zero-shot)"
        st.regimes["nowcast"] = self._forecast_regime("nowcast", tens, horizon, wx)

        # -------- multi-year regime ----------------------------------------
        st.stage = "decomposing long-range tensor"
        months = time_index(*_floor_range(events["timestamp"], "MS"), "MS")[-config.MAX_TIME_STEPS:]
        if len(months) >= config.LONG_RANGE_MIN_PERIODS and freq != "MS":
            wx_l = weather_loader.load(months[0], months[-1] + pd.offsets.MonthEnd(1), granularity="daily")
            tens_l = self.tensor_engine.build(events, st.cells, "MS", self.highlight_category,
                                              wx_l.frame, static, times=months)
            end = pd.Timestamp(config.LONG_RANGE_END, tz="UTC")
            h_l = len(pd.date_range(months[-1], end, freq="MS")) - 1
            if h_l > 0:
                st.stage = "forecasting long-range (zero-shot)"
                st.regimes["longrange"] = self._forecast_regime("longrange", tens_l, h_l, wx_l)
        else:
            st.notes.append(
                f"long-range regime disabled: {len(months)} monthly periods of history "
                f"< {config.LONG_RANGE_MIN_PERIODS} required for a multi-year forecast"
            )
        self._assemble_frames(st)

    def _run_backtest(self, st: PipelineState) -> None:
        reg = st.regimes.get("nowcast")
        if reg is None:
            return
        st.backtest_status = "running"
        try:
            st.backtest = run_backtest(
                events=st.events, cells=st.cells, freq=reg.tensor.freq,
                highlight_category=self.highlight_category, weather=reg.weather.frame,
                static=st.static, realized=reg.tensor.realized, times=reg.tensor.times,
                horizon=len(reg.horizon_times), forecaster=self.forecaster,
                tensor_engine=self.tensor_engine,
            )
            st.backtest_status = "ready"
        except Exception as exc:
            log.exception("backtest failed")
            st.backtest_status, st.backtest_error = "error", f"{type(exc).__name__}: {exc}"

    def _run_study(self, st: PipelineState) -> None:
        reg = st.regimes.get("nowcast")
        if reg is None:
            return
        st.study_status = "running"
        try:
            st.study = run_study(events=st.events, infra=st.infra, weather=reg.weather.frame,
                                 highlight_category=self.highlight_category,
                                 forecaster=self.forecaster, tensor_engine=self.tensor_engine)
            st.study_status = "ready"
        except Exception as exc:
            log.exception("study failed")
            st.study_status, st.study_error = "error", f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ #
    def _focus(self, events: pd.DataFrame, st: PipelineState) -> pd.DataFrame:
        """Keep the densest city-scale region (dumps often span several cities)."""
        coarse = [h3.latlng_to_cell(a, b, config.FOCUS_RESOLUTION)
                  for a, b in zip(events["latitude"], events["longitude"])]
        top = pd.Series(coarse).value_counts().index[0]
        keep_cells = set(h3.grid_disk(top, 1))
        mask = np.fromiter((c in keep_cells for c in coarse), bool, len(coarse))
        if not mask.all():
            st.notes.append(f"focused on densest region ({mask.sum()}/{len(mask)} events)")
        return events[mask].reset_index(drop=True)

    def _forecast_regime(self, name: str, tens: TensorResult, horizon: int, wx: WeatherResult) -> Regime:
        U_t = tens.temporal_factors                     # T × R_t
        out = self.forecaster.forecast(U_t.T, horizon)  # R_t × h
        fc = tens.project(out.point.T)
        lo_raw, hi_raw = tens.project(out.lo.T), tens.project(out.hi.T)
        lo, hi = np.minimum(lo_raw, hi_raw), np.maximum(lo_raw, hi_raw)
        surface = np.hstack([tens.denoised, fc])
        momentum = np.diff(surface, axis=1, prepend=surface[:, :1])
        step = pd.tseries.frequencies.to_offset(tens.freq)
        h_times = pd.date_range(tens.times[-1] + step, periods=horizon, freq=tens.freq)
        return Regime(name, tens, h_times, fc, lo, hi, momentum, wx)

    def _assemble_frames(self, st: PipelineState) -> None:
        frames: list[FrameRef] = []
        now = st.regimes["nowcast"]
        nt = now.tensor.times
        lr = st.regimes.get("longrange")
        if lr is not None:
            for i, t in enumerate(lr.tensor.times):
                if t < nt[0]:
                    frames.append(FrameRef(t, lr, i, "historical"))
        frames += [FrameRef(t, now, i, "historical") for i, t in enumerate(nt)]
        frames += [FrameRef(t, now, len(nt) + i, "forecast") for i, t in enumerate(now.horizon_times)]
        if lr is not None:
            T = len(lr.tensor.times)
            frames += [FrameRef(t, lr, T + i, "forecast") for i, t in enumerate(lr.horizon_times)
                       if t > now.horizon_times[-1]]
        st.frames = sorted(frames, key=lambda f: f.ts)
        self._frame_ts = [f.ts for f in st.frames]

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def resolve_frame(self, ts: datetime | None) -> FrameRef:
        frames = self.state.frames
        if not frames:
            raise LookupError("pipeline not ready")
        if ts is None:
            return next((f for f in reversed(frames) if f.kind == "historical"), frames[-1])
        t = pd.Timestamp(ts)
        t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
        i = bisect.bisect_right(self._frame_ts, t) - 1
        return frames[max(i, 0)]

    def frame_payload(self, ts: datetime | None) -> dict:
        st, prof = self.state, self.profile
        f = self.resolve_frame(ts)
        reg, tens = f.regime, f.regime.tensor
        T = len(tens.times)
        hist = f.kind == "historical"
        realized = tens.realized[:, f.idx] if hist else None
        denoised = tens.denoised[:, f.idx] if hist else None
        fc = reg.forecast[:, f.idx - T] if not hist else None
        lo = reg.lo[:, f.idx - T] if not hist else None
        hi = reg.hi[:, f.idx - T] if not hist else None
        momentum = reg.momentum[:, f.idx]
        surface = denoised if hist else fc

        horizon_label = _horizon_label(f, st)
        labels, cards = signals.generate(
            cells=st.cells, centers=st.centers, regime=reg.name, realized=realized,
            denoised=surface, forecast=fc, momentum=momentum, noun=self.event_noun,
            horizon_label=horizon_label,
        )

        features = []
        for i, cell in enumerate(st.cells):
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [h3_grid.cell_polygon(cell)]},
                "properties": {
                    "h3": cell,
                    "realized": _r(realized, i), "denoised": _r(denoised, i),
                    "forecast": _r(fc, i), "forecast_lo": _r(lo, i), "forecast_hi": _r(hi, i),
                    "momentum": round(float(momentum[i]), 4),
                    "signal": labels[i],
                },
            })

        return {
            "type": "FeatureCollection",
            "features": features,
            "meta": {
                "timestamp": f.ts.isoformat(), "kind": f.kind, "regime": reg.name,
                "freq": tens.freq, "horizon_label": horizon_label,
                "value_label": self.value_label, "momentum_unit": f"Δ{self.value_label}/{tens.freq}",
                "max_surface": float(np.max(surface)) if surface is not None and len(surface) else 0.0,
                "weather": self._weather_at(reg, f.ts),
            },
            "highlights": self._highlights(f) if hist else [],
            "vectors": _momentum_vectors(st.cells, st.centers, surface),
            "catchments": _catchments(cards),
            "signals": cards,
        }

    def _highlights(self, f: FrameRef) -> list[dict]:
        ev = self.state.events
        step = pd.tseries.frequencies.to_offset(f.regime.tensor.freq)
        sel = ev[(ev["timestamp"] >= f.ts) & (ev["timestamp"] < f.ts + step)
                 & (ev["category"] == self.highlight_category)]
        return [{"latitude": r.latitude, "longitude": r.longitude, "category": r.category,
                 "timestamp": r.timestamp.isoformat()} for r in sel.head(500).itertuples()]

    @staticmethod
    def _weather_at(reg: Regime, ts: pd.Timestamp) -> dict | None:
        w = reg.weather.frame
        if w.empty:
            return None
        idx = w.index.searchsorted(ts, side="right") - 1
        if idx < 0 or ts - w.index[idx] > pd.Timedelta(days=31):
            return None
        row = w.iloc[idx]
        return {k: (None if pd.isna(v) else round(float(v), 2)) for k, v in row.items()}


# ---------------------------------------------------------------------- #
def _floor_range(ts: pd.Series, freq: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    from engine.tensor_engine import floor_ts
    b = floor_ts(ts, freq)
    return b.min(), b.max()


def _r(arr: np.ndarray | None, i: int) -> float | None:
    return None if arr is None else round(float(arr[i]), 4)


def _horizon_label(f: FrameRef, st: PipelineState) -> str:
    if f.kind == "historical":
        return "realized"
    anchor = st.regimes["nowcast"].tensor.times[-1]
    delta = f.ts - anchor
    minutes = delta.total_seconds() / 60
    if minutes < 180:
        return f"T+{minutes:.0f} min"
    if minutes < 60 * 72:
        return f"T+{minutes / 60:.0f} h"
    if minutes < 60 * 24 * 90:
        return f"T+{minutes / 1440:.0f} d"
    return f"by {f.ts.strftime('%b %Y')}"


def _momentum_vectors(cells, centers, surface, top: int = 80) -> list[dict]:
    """Spatial gradient of the activity surface: arrows point toward rising activity."""
    if surface is None or not len(surface):
        return []
    lookup = {c: surface[i] for i, c in enumerate(cells)}
    out = []
    for i, c in enumerate(cells):
        lat0, lon0 = centers[i]
        gx = gy = 0.0
        for n in h3_grid.neighbors(c):
            if n not in lookup:
                continue
            lat1, lon1 = h3.cell_to_latlng(n)
            dx, dy = (lon1 - lon0) * math.cos(math.radians(lat0)), lat1 - lat0
            norm = math.hypot(dx, dy) or 1.0
            d = lookup[n] - surface[i]
            gx += d * dx / norm
            gy += d * dy / norm
        mag = math.hypot(gx, gy)
        if mag > 0:
            out.append((mag, i, gx / mag, gy / mag))
    out.sort(reverse=True)
    out = out[:top]
    if not out:
        return []
    max_mag = out[0][0]
    length = h3.average_hexagon_edge_length(config.H3_RESOLUTION, unit="m") * 1.6 / 111_320
    vecs = []
    for mag, i, ux, uy in out:
        lat0, lon0 = centers[i]
        scale = length * (0.35 + 0.65 * mag / max_mag)
        vecs.append({
            "from": [lon0, lat0],
            "to": [lon0 + ux * scale / math.cos(math.radians(lat0)), lat0 + uy * scale],
            "magnitude": round(mag / max_mag, 3),
        })
    return vecs


def _catchments(cards: list[dict], limit: int = 5) -> list[dict]:
    """Hex k-ring walking catchments around predicted spikes (≈ 80 m/min walking)."""
    spacing_m = h3.average_hexagon_edge_length(config.H3_RESOLUTION, unit="m") * math.sqrt(3)
    out, seen = [], set()
    for c in cards:
        if c["type"] not in ("DISPATCH", "VELOCITY_SURGE") or c["h3"] in seen:
            continue
        seen.add(c["h3"])
        rings = []
        for k in range(1, config.CATCHMENT_RINGS + 1):
            rings.append({
                "k": k, "walk_minutes": round(k * spacing_m / 80),
                "coordinates": h3_grid.ring_outline(list(h3.grid_disk(c["h3"], k))),
            })
        out.append({"h3": c["h3"], "type": c["type"], "rings": rings})
        if len(out) >= limit:
            break
    return out


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

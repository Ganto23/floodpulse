"""
Zero-shot forecasting of the latent temporal Tucker factors.

Backend resolution (FORECAST_BACKEND="auto"):
  1. Google TimesFM 2.5 (PyTorch)      — `pip install timesfm[torch]`
  2. Google TimesFM 1.x (PyTorch)      — older `timesfm` releases
  3. Amazon Chronos-Bolt (HF, PyTorch) — `pip install chronos-forecasting`
  4. Damped-trend Holt smoothing        — numpy-only, clearly reported as DEGRADED

All backends implement: forecast(series[n, T], horizon) -> (point, lo, hi) each [n, h].
The active backend name is exposed in /api/status so the UI never overclaims.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np

from config import CHRONOS_REPO, FORECAST_BACKEND, TIMESFM_REPO, TIMESFM_V1_REPO

log = logging.getLogger(__name__)


@dataclass
class ForecastOutput:
    point: np.ndarray
    lo: np.ndarray
    hi: np.ndarray


class _Backend:
    name = "base"
    zero_shot_transformer = False

    def forecast(self, series: np.ndarray, horizon: int) -> ForecastOutput:  # pragma: no cover
        raise NotImplementedError


class TimesFM25Backend(_Backend):
    name = "timesfm-2.5"
    zero_shot_transformer = True

    def __init__(self) -> None:
        import timesfm  # noqa: WPS433
        import torch

        torch.set_float32_matmul_precision("high")
        self._tfm = timesfm
        self.model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(TIMESFM_REPO)
        self._compiled_h = 0

    def _compile(self, horizon: int) -> None:
        if horizon <= self._compiled_h:
            return
        h = int(np.ceil(horizon / 128) * 128)
        self.model.compile(self._tfm.ForecastConfig(
            max_context=1024, max_horizon=h, normalize_inputs=True,
            use_continuous_quantile_head=True, fix_quantile_crossing=True,
        ))
        self._compiled_h = h

    def forecast(self, series: np.ndarray, horizon: int) -> ForecastOutput:
        self._compile(horizon)
        point, quant = self.model.forecast(horizon=horizon, inputs=[s.astype(np.float32) for s in series])
        point = np.asarray(point)[:, :horizon]
        quant = np.asarray(quant)[:, :horizon, :]   # [..., mean, q10..q90]
        return ForecastOutput(point, quant[..., 1], quant[..., -1])


class TimesFM1Backend(_Backend):
    name = "timesfm-1.0"
    zero_shot_transformer = True

    def __init__(self) -> None:
        import timesfm

        self.model = timesfm.TimesFm(
            hparams=timesfm.TimesFmHparams(backend="cpu", per_core_batch_size=32, horizon_len=128),
            checkpoint=timesfm.TimesFmCheckpoint(huggingface_repo_id=TIMESFM_V1_REPO),
        )

    def forecast(self, series: np.ndarray, horizon: int) -> ForecastOutput:
        out_p, out_lo, out_hi = [], [], []
        remaining, ctx = horizon, [s.astype(np.float32) for s in series]
        while remaining > 0:   # autoregressive roll-out beyond the 128-step head
            point, quant = self.model.forecast(ctx, freq=[0] * len(ctx))
            step = min(128, remaining)
            out_p.append(point[:, :step])
            out_lo.append(quant[:, :step, 1])
            out_hi.append(quant[:, :step, -1])
            ctx = [np.concatenate([c, p[:step]]) for c, p in zip(ctx, point)]
            remaining -= step
        return ForecastOutput(np.hstack(out_p), np.hstack(out_lo), np.hstack(out_hi))


class ChronosBackend(_Backend):
    name = "chronos-bolt"
    zero_shot_transformer = True

    def __init__(self) -> None:
        import torch
        from chronos import BaseChronosPipeline

        self.torch = torch
        self.pipe = BaseChronosPipeline.from_pretrained(CHRONOS_REPO, device_map="cpu",
                                                        torch_dtype=torch.float32)

    def forecast(self, series: np.ndarray, horizon: int) -> ForecastOutput:
        ctx = self.torch.tensor(series, dtype=self.torch.float32)
        q, mean = self.pipe.predict_quantiles(context=ctx, prediction_length=horizon,
                                              quantile_levels=[0.1, 0.5, 0.9])
        q = q.numpy()
        return ForecastOutput(mean.numpy(), q[..., 0], q[..., 2])


class DampedHoltBackend(_Backend):
    """Additive damped-trend exponential smoothing; parameters grid-searched per series."""

    name = "statistical-fallback (damped Holt)"

    GRID = [(a, b, phi) for a in (0.1, 0.3, 0.5, 0.8) for b in (0.01, 0.05, 0.2) for phi in (0.8, 0.9, 0.98)]

    def forecast(self, series: np.ndarray, horizon: int) -> ForecastOutput:
        # vectorized over series; loops only over grid × time
        Y = np.atleast_2d(series).astype(float)
        n, T = Y.shape
        steps = np.arange(1, horizon + 1)
        best_sse = np.full(n, np.inf)
        best_lvl, best_tr, best_phi = np.zeros(n), np.zeros(n), np.ones(n)
        for a, b, phi in self.GRID:
            lvl = Y[:, 0].copy()
            tr = (Y[:, 1] - Y[:, 0]) if T > 1 else np.zeros(n)
            sse = np.zeros(n)
            for t in range(1, T):
                pred = lvl + phi * tr
                sse += (Y[:, t] - pred) ** 2
                new_lvl = a * Y[:, t] + (1 - a) * pred
                tr = b * (new_lvl - lvl) + (1 - b) * phi * tr
                lvl = new_lvl
            better = sse < best_sse
            best_sse[better], best_lvl[better], best_tr[better], best_phi[better] = (
                sse[better], lvl[better], tr[better], phi)
        damp = np.cumsum(best_phi[:, None] ** steps[None, :], axis=1)
        point = best_lvl[:, None] + damp * best_tr[:, None]
        sigma = np.sqrt(best_sse / max(T - 2, 1))
        band = 1.2816 * sigma[:, None] * np.sqrt(steps)[None, :]
        return ForecastOutput(point, point - band, point + band)


_CANDIDATES = {
    "timesfm": (TimesFM25Backend, TimesFM1Backend),
    "chronos": (ChronosBackend,),
    "statistical": (DampedHoltBackend,),
}
_CANDIDATES["auto"] = _CANDIDATES["timesfm"] + _CANDIDATES["chronos"] + _CANDIDATES["statistical"]


class ForecastEngine:
    def __init__(self, preference: str = FORECAST_BACKEND) -> None:
        self.preference = preference
        self._backend: _Backend | None = None
        self._lock = threading.Lock()
        self.load_errors: list[str] = []

    @property
    def backend(self) -> _Backend:
        with self._lock:
            if self._backend is None:
                for cls in _CANDIDATES.get(self.preference, _CANDIDATES["auto"]):
                    try:
                        self._backend = cls()
                        log.info("forecast backend: %s", self._backend.name)
                        break
                    except Exception as exc:  # missing package, no weights, API drift
                        self.load_errors.append(f"{cls.name}: {type(exc).__name__}: {exc}"[:240])
                        log.warning("forecast backend %s unavailable: %s", cls.name, exc)
                if self._backend is None:
                    self._backend = DampedHoltBackend()
            return self._backend

    def describe(self) -> dict:
        b = self.backend
        return {"backend": b.name, "zero_shot_transformer": b.zero_shot_transformer,
                "load_errors": self.load_errors}

    def forecast(self, series: np.ndarray, horizon: int) -> ForecastOutput:
        series = np.nan_to_num(np.atleast_2d(series).astype(np.float64))
        try:
            return self.backend.forecast(series, horizon)
        except Exception as exc:
            if isinstance(self._backend, DampedHoltBackend):
                raise
            log.exception("forecast with %s failed; degrading", self._backend.name)
            self.load_errors.append(f"{self._backend.name} runtime: {exc}"[:240])
            self._backend = DampedHoltBackend()
            return self._backend.forecast(series, horizon)

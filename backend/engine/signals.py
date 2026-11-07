"""Automated decision signals from realized / denoised / forecast activity surfaces."""

from __future__ import annotations

import numpy as np

from config import ANOMALY_Z, DISPATCH_Z, SURGE_Z


def robust_z(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826
    # zero-inflated surfaces (most cells idle) collapse the MAD; floor with σ
    scale = max(mad, 0.5 * x.std(), 1e-9)
    return np.clip((x - med) / scale, -99, 99)


def _material(x: np.ndarray, frac: float = 0.15) -> np.ndarray:
    """Ignore numerically-tiny moves: |x| must be ≥ frac of the frame's max |x|."""
    peak = np.max(np.abs(x)) if len(x) else 0.0
    return np.abs(x) >= frac * peak if peak > 0 else np.zeros(len(x), bool)


def generate(
    *, cells: list[str], centers: list[tuple[float, float]], regime: str,
    realized: np.ndarray | None, denoised: np.ndarray, forecast: np.ndarray | None,
    momentum: np.ndarray, noun: str, horizon_label: str,
) -> tuple[list[str | None], list[dict]]:
    """
    Returns (per-cell signal label, signal cards). Rules:
      VELOCITY_SURGE  momentum z ≥ SURGE_Z          -> scale exposure / staff up
      MOMENTUM_DECAY  momentum z ≤ -SURGE_Z         -> unwind / reroute
      ANOMALY         (realized − denoised) z ≥ ANOMALY_Z, historical only
      DISPATCH        forecast z ≥ DISPATCH_Z and rising momentum, forward only
    """
    n = len(cells)
    labels: list[str | None] = [None] * n
    cards: list[dict] = []
    mz = robust_z(momentum)
    mom_ok = _material(momentum)

    def add(i: int, kind: str, z: float, severity: str, msg: str, action: str) -> None:
        if labels[i] is None or kind in ("ANOMALY", "DISPATCH"):
            labels[i] = kind
        lat, lon = centers[i]
        cards.append({"id": f"{kind}:{cells[i]}", "type": kind, "severity": severity,
                      "h3": cells[i], "latitude": lat, "longitude": lon, "z": round(float(z), 2),
                      "message": msg, "action": action})

    for i in np.where((mz >= SURGE_Z) & mom_ok)[0]:
        add(i, "VELOCITY_SURGE", mz[i], "high" if mz[i] >= 1.5 * SURGE_Z else "medium",
            f"ΔS/Δt +{momentum[i]:.3g}/bin — {noun} velocity surge ({mz[i]:.1f}σ)",
            "SCALE_UP: raise courier capacity & go long local foot-traffic exposure")
    for i in np.where((mz <= -SURGE_Z) & mom_ok)[0]:
        add(i, "MOMENTUM_DECAY", mz[i], "medium",
            f"ΔS/Δt {momentum[i]:.3g}/bin — momentum decaying ({mz[i]:.1f}σ)",
            "UNWIND: reroute couriers, reduce exposure")

    if realized is not None:
        resid = realized - denoised
        rz = robust_z(resid)
        for i in np.where((rz >= ANOMALY_Z) & _material(resid, 0.3) & (realized > 0))[0]:
            add(i, "ANOMALY", rz[i], "critical",
                f"realized {realized[i]:.3g} vs denoised {denoised[i]:.3g} — off-manifold spike ({rz[i]:.1f}σ)",
                "INVESTIGATE: transient event not explained by latent structure")

    if forecast is not None:
        fz = robust_z(forecast)
        for i in np.where((fz >= DISPATCH_Z) & (momentum > 0) & _material(forecast, 0.3))[0]:
            add(i, "DISPATCH", fz[i], "high",
                f"forecast {forecast[i]:.3g} {horizon_label} ({fz[i]:.1f}σ) with rising momentum",
                "DISPATCH: pre-position couriers / trigger entry order")

    order = {"critical": 0, "high": 1, "medium": 2}
    cards.sort(key=lambda c: (order[c["severity"]], -abs(c["z"])))
    return labels, cards[:40]

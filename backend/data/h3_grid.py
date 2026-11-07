"""Uber H3 hexagonal indexing for StandardSpatialEvent frames."""

from __future__ import annotations

import h3
import numpy as np
import pandas as pd

from config import H3_RESOLUTION


def index_events(df: pd.DataFrame, resolution: int = H3_RESOLUTION) -> pd.DataFrame:
    """Add an `h3` column (cell id at `resolution`)."""
    out = df.copy()
    out["h3"] = [h3.latlng_to_cell(la, lo, resolution)
                 for la, lo in zip(out["latitude"].to_numpy(), out["longitude"].to_numpy())]
    return out


def cell_counts(points: pd.DataFrame, cells: list[str], resolution: int = H3_RESOLUTION,
                weight: str | None = None, smooth_k: int = 0) -> np.ndarray:
    """
    Per-cell (optionally k-ring smoothed) sum of points/weights, aligned to `cells`.
    Used for static infrastructure layers (transit, footway metres, buildings).
    """
    if points is None or points.empty:
        return np.zeros(len(cells))
    ids = [h3.latlng_to_cell(a, b, resolution)
           for a, b in zip(points["latitude"].to_numpy(), points["longitude"].to_numpy())]
    w = points[weight].to_numpy(dtype=float) if weight else np.ones(len(ids))
    agg = pd.Series(w).groupby(pd.Index(ids)).sum()
    if smooth_k <= 0:
        return agg.reindex(cells, fill_value=0.0).to_numpy()
    lookup = agg.to_dict()
    return np.array([sum(lookup.get(n, 0.0) for n in h3.grid_disk(c, smooth_k)) for c in cells])


def cell_polygon(cell: str) -> list[list[float]]:
    """GeoJSON ring ([lon, lat], closed) for an H3 cell."""
    ring = [[lng, lat] for lat, lng in h3.cell_to_boundary(cell)]
    ring.append(ring[0])
    return ring


def cell_center(cell: str) -> tuple[float, float]:
    lat, lng = h3.cell_to_latlng(cell)
    return lat, lng


def neighbors(cell: str) -> list[str]:
    return [c for c in h3.grid_disk(cell, 1) if c != cell]


def catchment_rings(cell: str, k: int) -> list[list[str]]:
    """Hex rings 1..k (walking-catchment approximation: ~edge length × 2 per ring)."""
    return [list(h3.grid_ring(cell, i)) for i in range(1, k + 1)]


def ring_outline(cells: list[str]) -> list[list[list[float]]]:
    """Merged outline polygon(s) of a set of cells, as GeoJSON MultiPolygon coords."""
    shape = h3.cells_to_h3shape(cells)
    geo = shape.__geo_interface__
    coords = geo["coordinates"]
    return coords if geo["type"] == "MultiPolygon" else [coords]


def bbox_of(df: pd.DataFrame, pad: float = 0.002) -> tuple[float, float, float, float]:
    return (float(df["latitude"].min()) - pad, float(df["longitude"].min()) - pad,
            float(df["latitude"].max()) + pad, float(df["longitude"].max()) + pad)

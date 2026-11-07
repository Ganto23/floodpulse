"""
Phase 3: DEM catchment delineation and hydraulic lag features.

DEM       AWS Terrain Tiles (Terrarium PNG, SRTM/GMTED-derived, public, no key), mosaicked and sampled
          on a 121×121 grid around each gauge; the grid's half-width scales with the NRFA catchment area.
          (The Open-Meteo elevation API was tried first, but its free quota counts every point, and
          ~17k points exhausted it.)
Routing   priority-flood depression filling → D8 flow directions → flow accumulation
Outlet    the gauge is snapped to the cell within SNAP_KM whose upstream area best matches the
          official NRFA catchment area (when one exists), else to the max-accumulation cell
Features  DEM catchment area (validated vs NRFA), longest flow path L, relief, mean slope,
          outlet→centroid distance, Kirpich time of concentration
              Tc[min] = 0.0195 · L[m]^0.77 · S^-0.385      (S = relief / L)
          plus NRFA descriptors: DPSBAR (mean drainage-path slope), BFIHOST (baseflow index),
          SAAR (annual rainfall)
Truncation: if the delineated catchment touches the grid edge, it's flagged (area is a lower bound).

Output: data/rivers/catchments.json
"""

from __future__ import annotations

import heapq
import json
import math

import io

import numpy as np
import requests
from PIL import Image

from fetch_data import get_json
from multi_river_fetch import OUT, STATIONS

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TILE_DIR = OUT / "terrarium"
NRFA_URL = "https://nrfaapps.ceh.ac.uk/nrfa/ws/station-info"
NRFA_IDS = {"calder_mytholmroyd": "27088", "aire_armley": "27028", "calder_whalley": "71004",
            "eden_sheepmount": "76007", "greta_low_briery": "75009", "ribble_samlesbury": "71001",
            "kent_victoria_bridge": "73012", "derwent_ouse_bridge": "75003"}
DEFAULT_AREA = {"cragg_dauber_bridge": 15.0, "wharfe_otley": 600.0}   # only sizes the grid
SNAP_KM = 1.5
D8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def nrfa(station_id: str) -> dict:
    d = get_json(NRFA_URL, {"station": station_id, "format": "json-object",
                            "fields": "id,name,catchment-area,dpsbar,bfihost,saar-1961-1990,propwet,maximum-altitude"})
    return d["data"][0] if d.get("data") else {}


def _tile_xy(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _tile(z: int, x: int, y: int) -> np.ndarray:
    TILE_DIR.mkdir(parents=True, exist_ok=True)
    path = TILE_DIR / f"{z}_{x}_{y}.png"
    if not path.exists():
        for attempt in range(4):
            try:
                r = requests.get(TILE_URL.format(z=z, x=x, y=y), timeout=60)
                r.raise_for_status()
                path.write_bytes(r.content)
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768     # Terrarium encoding (m)


def dem_grid(lat: float, lon: float, half_km: float, n: int):
    lats = lat + np.linspace(-half_km, half_km, n) / 111.32
    lons = lon + np.linspace(-half_km, half_km, n) / (111.32 * math.cos(math.radians(lat)))
    LA, LO = np.meshgrid(lats[::-1], lons, indexing="ij")          # row 0 = north
    for z in range(12, 7, -1):                                     # finest zoom with ≤ 64 tiles
        x0, y0 = _tile_xy(LA.max(), LO.min(), z)
        x1, y1 = _tile_xy(LA.min(), LO.max(), z)
        if (int(x1) - int(x0) + 1) * (int(y1) - int(y0) + 1) <= 64:
            break
    xs, ys = range(int(x0), int(x1) + 1), range(int(y0), int(y1) + 1)
    mosaic = np.vstack([np.hstack([_tile(z, x, y) for x in xs]) for y in ys])
    fx = np.array([(_tile_xy(a, b, z)[0] - xs[0]) * 256 for a, b in zip(LA.ravel(), LO.ravel())])
    fy = np.array([(_tile_xy(a, b, z)[1] - ys[0]) * 256 for a, b in zip(LA.ravel(), LO.ravel())])
    # bilinear sample
    x0i, y0i = np.floor(fx).astype(int), np.floor(fy).astype(int)
    x0i = np.clip(x0i, 0, mosaic.shape[1] - 2); y0i = np.clip(y0i, 0, mosaic.shape[0] - 2)
    wx, wy = fx - x0i, fy - y0i
    zv = (mosaic[y0i, x0i] * (1 - wx) * (1 - wy) + mosaic[y0i, x0i + 1] * wx * (1 - wy)
          + mosaic[y0i + 1, x0i] * (1 - wx) * wy + mosaic[y0i + 1, x0i + 1] * wx * wy)
    return zv.reshape(n, n), LA, LO


def priority_flood(z: np.ndarray) -> np.ndarray:
    """Barnes et al. (2014) priority-flood with epsilon so every cell drains to the edge."""
    n, m = z.shape
    filled = z.copy()
    seen = np.zeros_like(z, bool)
    pq = []
    for i in range(n):
        for j in (0, m - 1):
            heapq.heappush(pq, (filled[i, j], i, j)); seen[i, j] = True
    for j in range(m):
        for i in (0, n - 1):
            if not seen[i, j]:
                heapq.heappush(pq, (filled[i, j], i, j)); seen[i, j] = True
    while pq:
        h, i, j = heapq.heappop(pq)
        for di, dj in D8:
            a, b = i + di, j + dj
            if 0 <= a < n and 0 <= b < m and not seen[a, b]:
                seen[a, b] = True
                filled[a, b] = max(filled[a, b], h + 1e-3)
                heapq.heappush(pq, (filled[a, b], a, b))
    return filled


def d8(filled: np.ndarray, dx_m: float):
    n, m = filled.shape
    down = np.full((n, m, 2), -1, int)
    for i in range(n):
        for j in range(m):
            best, arg = 0.0, None
            for di, dj in D8:
                a, b = i + di, j + dj
                if 0 <= a < n and 0 <= b < m:
                    s = (filled[i, j] - filled[a, b]) / (dx_m * math.hypot(di, dj))
                    if s > best:
                        best, arg = s, (a, b)
            if arg:
                down[i, j] = arg
    order = np.dstack(np.unravel_index(np.argsort(-filled, axis=None), filled.shape))[0]
    acc = np.ones((n, m))
    for i, j in order:
        a, b = down[i, j]
        if a >= 0:
            acc[a, b] += acc[i, j]
    return down, acc


def upstream(down: np.ndarray, outlet: tuple[int, int]) -> np.ndarray:
    n, m, _ = down.shape
    ups: dict[tuple[int, int], list] = {}
    for i in range(n):
        for j in range(m):
            a, b = down[i, j]
            if a >= 0:
                ups.setdefault((a, b), []).append((i, j))
    mask = np.zeros((n, m), bool)
    dist = np.full((n, m), np.nan)
    stack = [(outlet, 0.0)]
    while stack:
        (i, j), d = stack.pop()
        mask[i, j] = True
        dist[i, j] = d
        for (a, b) in ups.get((i, j), []):
            stack.append(((a, b), d + math.hypot(a - i, b - j)))
    return mask, dist


def analyse(slug: str) -> dict:
    river, label, _, lat, lon = STATIONS[slug]
    ref = nrfa(NRFA_IDS[slug]) if slug in NRFA_IDS else {}
    area_ref = ref.get("catchment-area") or DEFAULT_AREA.get(slug, 300.0)
    half = max(10.0, 1.6 * math.sqrt(area_ref))
    n = 121
    z, LA, LO = dem_grid(lat, lon, half, n)
    dx = 2 * half * 1000 / (n - 1)
    cell_km2 = (dx / 1000) ** 2
    filled = priority_flood(z)
    down, acc = d8(filled, dx)

    gi, gj = np.unravel_index(np.argmin((LA - lat) ** 2 + ((LO - lon) * math.cos(math.radians(lat))) ** 2), LA.shape)
    r = max(1, int(round(SNAP_KM * 1000 / dx)))
    win = [(i, j) for i in range(max(0, gi - r), min(n, gi + r + 1))
           for j in range(max(0, gj - r), min(n, gj + r + 1))]
    if ref.get("catchment-area"):
        outlet = min(win, key=lambda c: abs(acc[c] * cell_km2 - ref["catchment-area"]))
    else:
        outlet = max(win, key=lambda c: acc[c])
    mask, dist = upstream(down, outlet)
    area = float(mask.sum() * cell_km2)
    truncated = bool(mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())

    L_m = float(np.nanmax(dist[mask]) * dx)
    zc = z[mask]
    relief = float(zc.max() - z[outlet])
    S = max(relief / L_m, 1e-4) if L_m > 0 else 1e-4
    tc_h = 0.0195 * L_m ** 0.77 * S ** -0.385 / 60
    gy, gx = np.gradient(z, dx)
    slope = float(np.degrees(np.arctan(np.hypot(gx, gy)[mask])).mean())
    cy, cx = LA[mask].mean(), LO[mask].mean()
    cdist = math.hypot((cy - lat) * 111.32, (cx - lon) * 111.32 * math.cos(math.radians(lat)))

    return {
        "slug": slug, "river": river, "grid": {"n": n, "cell_m": round(dx), "half_width_km": round(half, 1)},
        "dem_area_km2": round(area, 1), "nrfa_area_km2": ref.get("catchment-area"),
        "area_ratio_dem_vs_nrfa": round(area / ref["catchment-area"], 3) if ref.get("catchment-area") else None,
        "truncated_by_grid": truncated, "longest_flow_path_km": round(L_m / 1000, 1),
        "relief_m": round(relief, 0), "outlet_elev_m": round(float(z[outlet]), 0),
        "mean_elev_m": round(float(zc.mean()), 0), "mean_slope_deg": round(slope, 2),
        "centroid_distance_km": round(cdist, 1), "kirpich_tc_h": round(tc_h, 2),
        "nrfa": {k: ref.get(k) for k in ("dpsbar", "bfihost", "saar-1961-1990", "propwet")} if ref else None,
    }


if __name__ == "__main__":
    out = {}
    for slug in STATIONS:
        try:
            out[slug] = analyse(slug)
        except Exception as exc:
            out[slug] = {"slug": slug, "error": f"{type(exc).__name__}: {exc}"[:300]}
        print(json.dumps(out[slug]))
    (OUT / "catchments.json").write_text(json.dumps(out, indent=1))

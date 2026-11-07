# UrbanPulse

Quantitative alt-data terminal. It takes crowdsourced spatial telemetry (Pokémon GO PokéStops, Gyms and Lures),
adds Open-Meteo weather and OpenStreetMap infrastructure, denoises it with Tucker tensor decomposition,
forecasts the latent temporal factors zero-shot (TimesFM), and emits automated spatial-momentum signals.

```
loader (DATASET_MODE) ─► StandardSpatialEvent ─► H3 res-9 grid
      + Open-Meteo ERA5 (rain/temp/wind)  + OSM (transit / footways / buildings)
  ─► X[cells × time × 8 features] ─► Tucker (TensorLy) ─► denoised surface + U_t latent factors
  ─► TimesFM / Chronos zero-shot forecast of U_t ─► projected per-cell forecasts (nowcast + monthly→2030)
  ─► ΔS/Δt momentum, robust-z signals, gradient vectors, k-ring catchments ─► FastAPI ─► deck.gl terminal
```

## Quick start

```bash
# backend (Python 3.11)
cd backend
uv venv --python 3.11 .venv && uv pip install -r pyproject.toml --extra dev
.venv/bin/uvicorn main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev      # http://localhost:5173 (proxies /api → :8000)
```

The API comes up immediately and runs the pipeline in the background. The first cold run makes live
Overpass and Open-Meteo calls (about 1–2 min). After that, responses are cached in `data/cache/`.
Put real datasets in `data/raw/` (see [data/raw/README.md](data/raw/README.md)).

### Enable the transformer forecaster

Without a transformer backend, the engine uses a damped-Holt model and the UI marks the
forecaster `[DEGRADED]`. To install one:

```bash
cd backend
uv pip install -r pyproject.toml --extra timesfm     # Google TimesFM 2.5 (PyTorch)
# or
uv pip install -r pyproject.toml --extra chronos     # Amazon Chronos-Bolt fallback
```

## Switching datasets

Set `DATASET_MODE` in `backend/config.py`, or use `URBANPULSE_DATASET_MODE=housing uvicorn main:app`.
The modes are `pokemon` | `osm` | `housing`. The math, forecaster, API and UI stay the same. Only the loader and
the UI descriptors (`MODE_PROFILES`) change. To add a mode, subclass `BaseDataLoader`, then register it in
`loaders/registry.py` and `MODE_PROFILES`.

Every setting can be overridden with an `URBANPULSE_<NAME>` environment variable (e.g. `URBANPULSE_TARGET_BBOX=40.70,-74.02,40.76,-73.96`).

## API

| Endpoint | Returns |
|---|---|
| `GET /api/status` | Source health (rows ingested, Open-Meteo rows, OSM node count, forecaster backend), tensor stats, pipeline log |
| `GET /api/timeline` | Frame list: monthly history → nowcast history → nowcast forecast → monthly forecast to 2030 |
| `GET /api/spatial-frame?timestamp=` | H3 GeoJSON with realized / denoised / forecast (+ 80% band) / ΔS/Δt / signal per cell, plus lures, momentum vectors, catchments and signal cards |
| `GET /api/infrastructure` | OSM transit nodes and pedestrian polylines for the map context layer |
| `POST /api/refresh` | Re-run the pipeline |

## Layout

```
backend/
  config.py               DATASET_MODE + MODE_PROFILES + all tunables
  loaders/                base.py (BaseDataLoader, StandardSpatialEvent), pokemon/osm/weather/housing loaders, registry
  data/h3_grid.py         H3 indexing, polygons, k-rings, static-layer aggregation
  engine/                 tensor_engine (Tucker), forecast_engine (TimesFM→Chronos→Holt), signals, pipeline
  main.py, schemas.py     FastAPI + Pydantic contracts
frontend/src/             App, MapCanvas (deck.gl + MapLibre), TimelineScrubber, TelemetrySidebar, SignalsPanel, lib/types.ts
data/raw/                 your real datasets (git-ignored)
```

## Notes on honesty (for judges)

- The status panel shows exactly which source fed each layer: `ONLINE`, `DEGRADED` (fallback in use) or `OFFLINE`.
- The multi-year regime only switches on with at least 12 months of real history. The nowcast bin size
  coarsens automatically (e.g. 15 min → 3 h) when the stream is too sparse, and the pipeline log records the change.
- With the OSM fallback, timestamps are *last-edit* times, so recent months are over-represented. Use a real
  scanner dump to get true foot-traffic dynamics.

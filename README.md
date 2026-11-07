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
Put real datasets in `data/raw/` (see [data/raw/README.md](data/raw/README.md)). For the Pokémon demo, run
`./scripts/fetch_kaggle_predictemall.sh` first. It downloads 296k real 2016 spawn sightings, and the pipeline
focuses on Prague by default.

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
| `GET /api/evaluation` | Pre-registered dev→holdout study: forecast skill at the chosen scale, spatial persistence, OSM→activity correlations |
| `GET /api/backtest` | Rolling-origin out-of-sample evaluation: UrbanPulse vs. no-denoise ablation, persistence, historical mean, t−24h, zero floor |
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

## Backtest

After the map goes live, the pipeline runs `engine/backtest.py`. At 24 origins spread over the back half of the
history, it refits everything on the data before that origin only: the scaler, Tucker and the forecaster. It then
forecasts the next 90 minutes per H3 cell and scores the result against the real sightings. Windows with fewer than
20 sightings are scanner outages, so they're excluded and counted. Metrics are pooled WAPE, allocation (share)
error, and precision@K. Results appear in the sidebar and at `/api/backtest`.

Results on Kaggle Prague (res 9, 15-min bins, damped-Holt forecaster, 15 valid origins):

| model | WAPE ↓ | share err ↓ | P@20 ↑ |
|---|---|---|---|
| **UrbanPulse** | **1.232** | 0.877 | 0.163 |
| same forecaster, no denoising | 1.426 | 0.830 | 0.240 |
| persistence | 1.460 | 0.816 | 0.227 |
| historical mean | 1.605 | 0.876 | 0.183 |
| seasonal t−24h | 1.704 | 0.928 | 0.090 |
| predict zero | 1.000 | 1.000 | — |

UrbanPulse has 16% lower WAPE than persistence and 14% lower than the same forecaster without denoising. But
per-cell 15-min counts are so sparse that no model beats predicting zero on WAPE. On *where* activity lands
(share error, P@K), persistence and the raw forecaster do as well or better. Re-run after enabling TimesFM.

## Holdout correlation study (`engine/evaluation.py`)

The protocol was fixed before any results were seen. The **final 48 h** are held out. Scale and metric are chosen
on the earlier dev period only, from business-motivated candidates: H3 res 9/8/7 (block, neighbourhood or courier
zone) × 90 min, 3 h or 6 h decision windows. The selection rule is the highest dev Pearson(log1p forecast,
log1p actual). The holdout is then scored once. Spearman only counts cells active during *training*, because
conditioning on "active in either period" is Berkson-biased.

Dev selected **res 7 (~5 km² courier zones) × 6 h windows**. Holdout results (Prague, damped-Holt forecaster):

| Test | Result |
|---|---|
| A. Forecast, 7 windows: Pearson(log) / Spearman / WAPE | UrbanPulse 0.34 / 0.24 / **0.93** · no-denoise 0.39 / 0.23 / 1.02 · persistence **0.47 / 0.41** / 1.34 · hist. mean 0.38 / 0.32 / 1.63 |
| B. Spatial persistence (dev rate → holdout rate per zone) | Pearson(log) **0.65**, Spearman 0.45, 50% of top-decile zones stay top-decile |
| C. OSM → activity, 93 of 101 zones covered | transit r = **0.52**, pedestrian network r = 0.45, buildings r = 0.26 (holdout). OLS fit on dev: R² 0.25 in-sample, 0.16 spatial-block CV, 0.14 holdout |

Reading these results: activity is predictable **in space** (B), and open infrastructure data explains a real share of
*where* players were (C). Only UrbanPulse beats the predict-zero floor on volume (WAPE < 1). For **ranking zones over
the next 6 h**, though, simple persistence wins. A has only 7 holdout windows, so treat its differences as indicative.

## Notes on honesty (for judges)

- The status panel shows exactly which source fed each layer: `ONLINE`, `DEGRADED` (fallback in use) or `OFFLINE`.
- The multi-year regime only switches on with at least 12 months of real history. The nowcast bin size
  coarsens automatically (e.g. 15 min → 3 h) when the stream is too sparse, and the pipeline log records the change.
- The Kaggle dataset covers only 6 days. The multi-year regime stays off in Pokémon mode, so the 2026–2030 view
  is only available in `osm` or `housing` mode.
- OSM infrastructure is fetched in Overpass tiles that cover the whole study area (21 tiles for Prague; the first
  run takes ~10 min, then it's cached). Coverage checks use only the tiles that actually loaded.
- With the OSM fallback, timestamps are *last-edit* times, so recent months are over-represented. Use a real
  scanner dump to get true foot-traffic dynamics.

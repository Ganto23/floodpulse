# FloodPulse

**Rain-augmented river-level forecasting for 9 northern UK gauges, built only from free public data and tested
the way a quant would test a signal: held out, ablated, and audited.**

> **Headline:** real, archived rain forecasts cut 6–24 h river-level forecast error by a median **25–45%** across
> 9 gauges. The baseline is a model using river history alone; the range runs from strictly-public 48 h-old
> forecasts to 24 h-old ones. The gain is positive at **9/9** gauges.
> **The bottleneck isn't the river model, it's rain-forecast quality.** With real 2024 forecasts, the system catches
> 46% of high-level crossings with ~1.7 h mean warning. With a perfect rain forecast, the same model warns ~14–15 h
> ahead on held-out mega-storms.

The dashboard is a **backtest replay**, not live telemetry. Everything you see is held-out model output. →
[`floodpulse-ui/`](floodpulse-ui) · full evidence: [`eval_harness/REPORT_FLOODPULSE_FINAL.md`](eval_harness/REPORT_FLOODPULSE_FINAL.md) ·
hostile audit: [`eval_harness/AUDIT_FLOODPULSE.md`](eval_harness/AUDIT_FLOODPULSE.md)

---

## 1. Alternative data, ingested raw

| Source | What | Why it's alt-data |
|---|---|---|
| **EA Hydrology API** | 15-min river stage, 10 gauges, 2019–2024 (~1.6 M readings) | sensor telemetry, not a vendor product |
| **EA tipping-bucket rain gauges** | 3 nearest per river, hourly | ground truth for rain; reanalysis smooths convective cells |
| **Open-Meteo Previous-Runs** | *issued* day-ahead NWP rain forecasts, archived as issued | the only honest way to backtest "with forecasts": no hindsight |
| **Open-Meteo ERA5** | rain, soil moisture (0–7, 7–28 cm), snowfall | soil saturation decides whether rain becomes runoff |
| **AWS Terrain Tiles (SRTM)** | DEM, mosaicked per catchment | physical routing |
| **NRFA** | official catchment areas and descriptors | external validation of our DEM delineation |

Two ingestion failures were handled rather than hidden:
- The EA's gateway throttled parallel bursts, so ingestion runs sequentially with backoff.
- Open-Meteo's elevation quota counts per point and ran out, so the DEM switched to terrain tiles.

## 2. Physical invariants before black-box ML

- **Catchments from first principles.** Priority-flood depression filling, D8 flow routing and flow accumulation on a
  121×121 DEM grid per gauge. DEM catchment areas match NRFA within **5% at 7 of 8** referenced gauges. (The outlet
  is snapped to the NRFA area, so this is partly by construction. Cragg Brook, with no reference, snapped onto the
  Calder. Both are disclosed.)
- **Hydraulic lag.** Kirpich time of concentration from longest flow path and relief: 2.4 h (Calder) to 13.6 h
  (Eden). Against measured rain→peak lags: **Spearman ρ = 0.64, p = 0.064, n = 9, not significant.** It matches
  8 rivers within ~3 h and **misses the lake-fed Derwent** (4.3 h vs 39 h) because lake storage isn't modelled.
  That's a known physics gap, diagnosed after the fact.
- **Runoff physics as features.** Soil-saturation index × rain intensity², plus "arrival rain": rain falling one
  DEM lag before the target hour.

## 3. Model: zero-shot foundation model + residual surge booster

```
EA level history ──► TimesFM 2.5 (zero-shot, 512 h context) ──► 24 h trajectory
                                                   │
rain gauges, soil saturation, DEM lag, issued/observed future rain ──► HistGradientBoosting on TimesFM residual
                                                   │      (quantile loss q=0.6, ×5 weight in high-runoff states)
                                                   ▼
                                  FloodPulse forecast (+ approximate 80% band)
```

- **Why a residual booster:** TimesFM alone extrapolates calmly and *doesn't anticipate surges*. On storm windows it
  under-predicts crests by ~93% of the rise. The booster learns when TimesFM under-shoots.
- **Real-forecast result (2024, 9 gauges):** **−25% MAE vs TimesFM, −41% vs persistence, −45% on surge hours**, and
  better at 9/9 gauges.
- **Ablation:** the physics features add little *on top of* the booster. They extend storm warnings with perfect
  rain (15.4 vs 11.4 h on Ciara) but raise false alarms. Most of the gain is the booster itself, and we say so.

## 4. Evaluation design (where the honesty lives)

- **Held-out everything:**
  - 2024 is held out entirely.
  - Storms Ciara/Dennis (Feb 2020) and Babet (Oct 2023) are excluded ±7 days from training.
  - Every scaler and threshold is fit on training data only.
- **Three rain-information regimes, never mixed up:**
  - *past rain only* (realistic floor);
  - *real issued forecasts* (deployable, 2024);
  - *perfect future rain* (upper bound, labelled as such everywhere).
- **Forecast-latency stress test:** results re-run with 48 h-old forecasts that were certainly public.
- **Metrics that matter for warnings:** crest magnitude and timing error, sustained-warning lead time, hit rate,
  false-alarm ratio. Small samples are reported with Wilson 95% CIs (Babet crest capture 3/7 = 43%, CI 16–75%).

| | Real issued forecasts (2024) | Perfect rain (upper bound) |
|---|---|---|
| Threshold crossings caught | **46%** of 61 (CI 34–58%) | 79% |
| Mean sustained warning | **1.7 h** | 5.4 h (2024) · 15.4 h Ciara · 13.8 h Babet |
| Storm crest under-prediction (median, % of rise) | — (no archived forecasts pre-2024) | −55% Ciara · −30% Babet |

### Unseen rivers (leave-one-river-out)

Every number above uses a booster trained on that river's own history (2019–2023), tested on its 2024. To test a
river the model has never seen, [`eval_harness/loro.py`](eval_harness/loro.py) trains **one shared booster on the
other rivers only** and scores it on the held-out river's 2024, using issued rain forecasts. Levels are scaled by
each river's own pre-2024 range, so one model serves rivers of different size. As a reference, each river's own
booster was retrained with identical settings (2024 origins every 3 h). Results are in
[`results/loro/loro.json`](eval_harness/results/loro/loro.json).

| Error reduction vs TimesFM (2024, issued forecasts) | Own-river booster | **Unseen river** |
|---|---|---|
| Median, 9 rivers | −25% (better at 9/9) | **−18% (better at 8/9)** |
| Median excluding Derwent | — | −19% |
| At +6 h / +12 h / +24 h | −19% / −23% / −28% | −10% / −16% / −23% |

- **It transfers to the 8 rainfall-driven rivers.** Unseen-river error is within 0–2 mm of the own-river model on
  5 of them. It's worse on the Eden (77 vs 72 mm) and the Ribble (88 vs 78 mm), but still well ahead of TimesFM.
- **It fails on the lake-fed Derwent:** 54 mm error vs TimesFM's 18 mm (3× worse). The shared model learned
  "rain → sharp rise" from flashy rivers. Bassenthwaite Lake absorbs that rise, so the model over-predicts
  (bias +25 mm). Catchment descriptors (area, Tc, BFIHOST, SAAR) didn't help, because no training river has a
  lake. This is the same physics gap as the DEM-lag miss. Deploying to a new river needs a check that it
  resembles the training rivers, or a lake-storage term.
- We did not tune anything after seeing these results.

## 5. Radical honesty: what this is *not*

- **Not a comparison with Environment Agency operational forecasts,** which aren't publicly archived. Our baseline is
  "river history without rain."
- **Not an early-warning system with today's forecasts.** ~2 h mean lead isn't enough. The pitch is that rain
  forecasts are the bottleneck, and we quantify how much better forecasts would be worth (up to ~14 h).
- **Not proven on every unseen river.** A shared model works on unseen rainfall-driven rivers (−18% vs TimesFM) but fails on the lake-fed Derwent; see "Unseen rivers" above.
- **Not a forward-in-time storm test.** Storm-window models were fit on 2019–2023, which includes years after Ciara.
- **Known data issues:**
  - 7 tipping-bucket artifacts pass QC (1 in the test set, with measured impact ≤ 0.11 m);
  - up to 13% of hours fall back from gauge rain to ERA5;
  - ERA5 isn't real-time.
- **Corrected along the way:** the first "River Calder" gauge was actually Cragg Brook. The real Calder gives
  −37% / −44% / −50%. The DEM-lag correlation fell from 0.88 to 0.64 once the Derwent finished. Both corrections
  are in the record.

## Run it

```bash
# evaluation harness (Python 3.11)
cd eval_harness && uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python \
  pandas numpy scipy statsmodels requests pillow scikit-learn torch "jax[cpu]" \
  "timesfm[torch,xreg] @ https://github.com/google-research/timesfm/archive/refs/heads/master.zip"
.venv/bin/python multi_river_fetch.py      # EA + Open-Meteo ingestion (sequential, cached)
.venv/bin/python multi_river_phase1.py     # cross-gauge forecast-value test
.venv/bin/python elevation_features.py     # DEM catchments, Kirpich lag, geometry export
FP_DUMP=results/dashboard FP_OUT=results/dashboard .venv/bin/python floodpulse_stress.py   # ~45 min
.venv/bin/python floodpulse_report.py && .venv/bin/python audit_forecast_lag.py
.venv/bin/python export_dashboard.py       # → floodpulse-ui/public/data

# dashboard
cd ../floodpulse-ui && npm install && npm run dev   # http://localhost:5174
```

`docs/URBANPULSE.md` documents the earlier UrbanPulse prototype in this repo.

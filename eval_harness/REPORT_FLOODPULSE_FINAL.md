# FloodPulse: final stress-test report

**Data:** 10 northern UK river gauges (Pennines + Lake District), Sep 2019 → Dec 2024, hourly, all real public data:
- EA Hydrology 15-min levels: ~1.6 M readings;
- EA tipping-bucket rain gauges: 3 per river, within 15 km;
- Open-Meteo ERA5 (rain, soil moisture, snow, temperature);
- Open-Meteo Previous-Runs archived **issued** day-ahead NWP rain forecasts (2024 only);
- NRFA catchment descriptors;
- AWS Terrain Tiles DEM.

**Code:** `multi_river_fetch.py` → `multi_river_phase1.py` → `elevation_features.py` → `floodpulse_stress.py` →
`floodpulse_report.py`. All tables are in `results/floodpulse_tables.md`; raw numbers are in
`results/floodpulse_summary.json` and `results/floodpulse/<gauge>.json`.

> **Correction to the earlier FloodPulse result.** The gauge first used as "River Calder @ Mytholmroyd" is
> actually *Mytholmroyd Dauber Bridge on Cragg Brook*, a tributary. The real River Calder gauge at Mytholmroyd
> (NRFA 27088) is included here and gives −37% / −44% / −50%, so the original finding holds for the correct river.

## Headline metrics

| Metric (across gauges) | Result |
|---|---|
| **Mean error reduction:** real issued rain forecasts vs river-history-only model (linear, 9 gauges, Aug–Dec 2024) | median **−32% @6 h, −43% @12 h, −45% @24 h**; 24 h range −19% (lake-fed Derwent) to −57% |
| **Mean error reduction:** TimesFM + surge booster with **real issued forecasts** (2024, 9 gauges, all hours) | median **−25% vs TimesFM**, **−41% vs persistence**; surge hours (>P95) **−45% vs TimesFM**. Beats TimesFM at **9/9** gauges |
| **Storm Babet peak capture** (crest within ±20% of rise and ±3 h; 7 gauges) | perfect rain forecast: **43% at 12 h lead**, 0% at 6 h lead · past rain only: **0% at 12 h**, 17% at 6 h · TimesFM alone: 0% / 17% |
| **Average lead-time warning window** (sustained warning before crossing the P99 level; mean over all events, misses = 0 h) | **real 2024 forecasts: 1.7 h** (3.7 h when caught; 46% of 61 events caught; false-alarm ratio 0.17) · perfect forecast, storms: **15.4 h (Ciara/Dennis, 25 events) / 13.8 h (Babet, 5)** · past rain only, storms: 3.0 h / 1.4 h |
| DEM travel time vs measured rain→peak lag (9 gauges) | Spearman **0.64 (p = 0.064, not significant)** · excluding the lake-regulated Derwent (post hoc): 0.88 (p = 0.004) |

## Phase 1: multi-river generalisation ✅

All 9 gauges with 2023–24 data show weather correlations of **r = 0.58–0.73** (soil moisture or 24 h rain; Bretherton
effective-n p < 0.05). Real issued rain forecasts cut forecast error at **every** gauge:

| Gauge | Best feature (r, lag) | Real fc 6 h | 12 h | 24 h | Perfect-fc bound 24 h | R² 24 h: AR → +weather |
|---|---|---|---|---|---|---|
| Calder @ Mytholmroyd | soil 7–28 cm (+0.64, 1 h) | −37% | −44% | −50% | −61% | 0.12 → 0.56 |
| Cragg Brook @ Dauber Br. | soil 7–28 cm (+0.67, 1 h) | −35% | −38% | −45% | −56% | 0.38 → 0.66 |
| Aire @ Armley (Leeds) | soil 7–28 cm (+0.68, 1 h) | −22% | −30% | −42% | −55% | 0.45 → 0.68 |
| Calder @ Whalley | rain 24 h (+0.73, 1 h) | −42% | −56% | −57% | −53% | 0.13 → 0.63 |
| Eden @ Sheepmount (Carlisle) | soil 7–28 cm (+0.67, 6 h) | −31% | −43% | −41% | −72% | 0.37 → 0.63 |
| Wharfe @ Otley | soil 7–28 cm (+0.58, 4 h) | −27% | −34% | −43% | −49% | 0.07 → 0.47 |
| Ribble @ Samlesbury | rain 24 h (+0.71, 5 h) | −32% | −51% | −57% | −60% | 0.13 → 0.62 |
| Kent @ Victoria Br. (Kendal) | rain 24 h (+0.71, 1 h) | −52% | −54% | −54% | −80% | 0.24 → 0.65 |
| Derwent @ Ouse Br. (lake-fed) | soil 7–28 cm (+0.66, 25 h) | −25% | −28% | −19% | −69% | 0.95 → 0.96 |
| **median** | | **−32%** | **−43%** | **−45%** | | |

Greta was excluded: its level record stops in 2020. **The baseline here is a model using river history alone. This is
not a comparison with Environment Agency flood forecasts.**

## Phase 2: mega-storm stress test ⚠️

The storms predate the forecast archive, so each one is bracketed by two variants: **past rain only** (a realistic
floor) and **actual future rain** (a perfect-forecast ceiling). The booster was never trained on these windows
(storm ±7 days excluded) or on 2024.

| Storm · variant | Model | Crest capture @6 h / @12 h | Median peak error (% of rise) | Mean \|timing error\| |
|---|---|---|---|---|
| Ciara/Dennis · perfect fc | TimesFM | 0% / 0% | −93% | 6.8 h |
| | **TimesFM + booster** | **17% / 0%** | **−55%** | **2.8 h** |
| Ciara/Dennis · past only | TimesFM + booster | 0% / 0% | −75% | 4.4 h |
| Babet · perfect fc | TimesFM | 17% / 0% | −92% | 5.4 h |
| | **TimesFM + booster** | **0% / 43%** | **−30%** | **1.7 h** |
| Babet · past only | TimesFM + booster | 17% / 0% | −74% | 4.8 h |

(n = 6–7 gauges per storm and lead.)
- **Crests are systematically under-predicted, by every model in every variant.** The booster cuts peak error from
  ~−93% to −30…−55% of the rise and timing error from ~6 h to ~2–3 h, but only when future rain is known.
- **Without a rain forecast, nothing anticipates a storm crest.**
- Ciara's record crests (Aire 4.13 m vs a P99 of 2.38 m; Eden 6.02 m) are where under-prediction is worst.

## Phase 3: elevation and catchment topography ✅ / ⚠️

**Catchment delineation** (priority-flood + D8 on Terrarium DEM tiles, 121 × 121 grid): DEM areas match the
official NRFA areas within 5% at **7 of 8** gauges (Ribble 0.83).
- **Caveat:** the outlet was snapped to the cell whose area best matches NRFA, so this agreement is partly by
  construction.
- **Cragg Brook failed:** with no NRFA reference, it snapped onto the larger Calder, so its DEM features are unreliable.

**Hydraulic lag (Kirpich Tc)** ranges from 2.4 h (Calder) to 13.6 h (Eden). Against the measured rain→peak lag:

| | Aire | Calder-M | Calder-W | Eden | Greta | Kent | Ribble | Wharfe | **Derwent** |
|---|---|---|---|---|---|---|---|---|---|
| Kirpich Tc (h) | 11.3 | 2.4 | 4.8 | 13.6 | 2.6 | 2.7 | 10.0 | 10.0 | **4.3** |
| Empirical lag (h) | 10 | 4 | 5 | 17 | 5 | 6 | 10 | 11 | **39** |

- **Agreement is close everywhere except the Derwent,** where Bassenthwaite Lake buffers floods for more than a day.
  Kirpich models only overland and channel flow.
- **Across all 9, Spearman = 0.64 (p = 0.064).** Excluding Derwent gives 0.88 (p = 0.004). That exclusion has a
  physical reason (the lake was noted in Phase 1), but it was made after seeing the result.
- **Next fix:** add a lake/reservoir storage term, e.g. from the NRFA FARL index.

**Lead-time early warning** (threshold = training-period P99; sustained warning lead time; false-alarm ratio):

| Test set · rain info | events | TimesFM: caught / mean lead / FAR | **TimesFM + booster** |
|---|---|---|---|
| 2024 · **real issued forecasts** | 61 | 31% / 0.4 h / 0.08 | **46% / 1.7 h / 0.17** |
| 2024 · past only | 61 | 66% / 1.0 h / 0.14 | 79% / 2.1 h / 0.17 |
| 2024 · perfect forecast | 61 | 66% / 1.0 h / 0.14 | 79% / 5.4 h / 0.26 |
| Ciara/Dennis · past only | 25 | 92% / 2.1 h / 0.03 | 100% / 3.0 h / 0.02 |
| Ciara/Dennis · perfect forecast | 25 | 92% / 2.1 h / 0.03 | **100% / 15.4 h / 0.01** |
| Babet · past only | 5 | 80% / 1.0 h / 0.01 | 80% / 1.4 h / 0.03 |
| Babet · perfect forecast | 5 | 80% / 1.0 h / 0.01 | **100% / 13.8 h / 0.01** |

- **With deployed forecasts, catch rate is lower than with past rain only (46% vs 79%).** The booster is trained on
  observed rain, and issued day-ahead forecasts under-predict heavy rain, so they suppress warnings. Training on
  issued forecasts needs a longer archive than the ~10 months currently available.
- **The 12–16 h storm warnings are an upper bound,** reachable only with near-perfect rain forecasts.

## Phase 4: non-linear surge correction ✅ (modest physics gain)

The booster is `HistGradientBoosting` on the TimesFM residual, with quantile loss q = 0.6 and ×5 weight when
runoff force (SSI · rain²) is in its top decile. Settings were fixed a priori, not tuned on test.
- **It's the largest single improvement in the study:** surge-hour error is −45% vs TimesFM with real forecasts and
  −60% with perfect ones, at every gauge.
- **The physics features themselves (runoff force, SSI, DEM-lag arrival rain) add little on top of the booster.**
  Overall MAE is near-identical (deployed: 0.056 vs 0.056 on the Aire, for example). They give small surge gains at
  most gauges, and longer storm warnings with perfect rain (15.4 vs 11.4 h Ciara; 13.8 vs 11.4 h Babet), at the
  cost of more false alarms (2024 deployed FAR 0.17 vs 0.12).
- Most of the gain comes from the booster learning *when TimesFM under-shoots*, not from the engineered physics.

## Verdict

| Claim | Status |
|---|---|
| Real weather forecasts substantially improve river-level forecasts, across rivers | ✅ **Proven** on 9/9 gauges (median −32…−45%) |
| A TimesFM + surge booster beats TimesFM and persistence in deployment conditions | ✅ **Proven** (−25% / −41% MAE, −45% surge MAE, 9/9 gauges) |
| DEM physics predicts each river's response time | ⚠️ **Mostly**: 8 of 9 rivers within ~3 h; fails on the lake-fed river; not significant across all 9 |
| Storm crests can be predicted accurately hours ahead | ❌ **Not yet**: crests under-predicted by 30–55% of the rise even with perfect rain; 0–43% captured |
| Hours of advance flood warning with today's forecasts | ❌ **Not supported**: 1.7 h mean, 46% of events caught |
| 12+ h warnings are achievable given good rain forecasts | ✅ as an **upper bound** (15.4 h / 13.8 h on held-out storms) |

**Recommendation: GO, but as a better river-level forecaster, not as an early-warning system.** The defensible
pitch: *"Across 9 northern UK rivers, real rain forecasts plus a surge-aware TimesFM cut river-level forecast error
by a quarter to a half. On held-out mega-storms, the same model gives 14–15 h of warning when rain forecasts are
accurate, so forecast rain quality is the bottleneck."*

**Main limits:**
- one deployment test year (2024), and storms tested only with past or perfect rain;
- the baseline is not the EA's operational forecast;
- the booster was trained on observed rather than issued rain;
- lake storage is missing from the travel-time feature.

# Quantitative Feasibility Report

All data comes from real public APIs. The period is 2023-01-01 → 2024-12-31, hourly (17,544 h per idea).
- **Split:** DEV is the first 80%; TEST is the last 20%, from 2024-08-07 19:00 UTC. Every fit uses DEV only.
- **Reproduce:** `fetch_data.py` → `check_correlation.py` → `test_timesfm.py`. Raw JSON is in `results/`.

| Idea | Target Y (source) | Exogenous X (source) | Coverage |
|---|---|---|---|
| **GridPulse** | GB national demand, INDO (Elexon BMRS) | temperature, heating degrees, solar radiation, wind: 5-city ERA5 (Open-Meteo) + archived day-ahead NWP forecasts | 35,086 half-hours, 100% |
| **FloodPulse** | River Calder stage @ Mytholmroyd (EA Hydrology, 15-min) | catchment rain, 6 h / 24 h rain, soil moisture 0–7 / 7–28 cm, temperature (ERA5) + archived NWP forecasts | 69,206 readings, 98.6% |
| **AirPulse** | NO₂ @ Marylebone Rd MY1 (LAQN) | wind, boundary-layer height, temperature, rain (ERA5) + archived NWP forecasts | 15,889 h, 90.6% |

## 1. Validated correlations (|r| > 0.40, autocorrelation-corrected p < 0.05)

The p-values use an effective sample size (Bretherton 1999), not the naive n ≈ 14,000. The "anomaly" view removes
the hour-of-week cycle, so that clock-driven co-movement doesn't count as signal.

| Idea | Feature (view) | best lag | Pearson r | Spearman ρ | n_eff | p_eff |
|---|---|---|---|---|---|---|
| Grid | heating degrees (anomaly) | 1 h | **+0.81** | +0.79 | 142 | 5e-34 |
| Grid | temperature (anomaly) | 1 h | **−0.80** | −0.81 | 134 | 1e-31 |
| Grid | solar radiation (anomaly) | 1 h | **−0.72** | −0.73 | 407 | 5e-67 |
| Flood | soil moisture 7–28 cm | 1 h | **+0.67** | +0.93 | 25 | 3e-4 |
| Flood | soil moisture 0–7 cm | 4 h | **+0.64** | +0.89 | 37 | 2e-5 |
| Flood | rain, 24 h accumulation | 1 h | **+0.57** | +0.48 | 59 | 3e-6 |
| Flood | rain, 6 h accumulation | **4 h** | **+0.46** | +0.34 | 256 | 1e-14 |
| Air | boundary-layer height (anomaly) | 1 h | −0.35 ✗ | −0.37 | 859 | 1e-25 |
| Air | wind speed (anomaly) | 1 h | −0.29 ✗ | −0.30 | 1166 | 1e-24 |

- **Mechanisms check out:**
  - Flood: 6-hour rain peaks at a 4-hour lag, the Pennine catchment's response time.
  - Grid: demand falls with warmth and sunshine (rooftop solar is invisible to the transmission grid).
  - Air: NO₂ rises as the boundary layer and wind drop, but weakly. **Air has no feature above |r| = 0.40.**
- **Granger tests (lag 24) give p < 1e-3 for almost every pair.** At n ≈ 14,000 that mostly reflects sample size, so the
  out-of-sample tests below are the discriminating evidence.
- **Weather alone, out of sample (OLS on best lags, TEST R²):** grid **0.76** (anomaly), flood 0.28, air −0.64.
  Air fails because its 2024 level shifted, likely the ULEZ effect.

### Does weather add forecast value beyond Y's own history? (TEST, error reduction vs AR(24))

| Horizon | Grid: past wx | Grid: **real issued forecasts** | Grid: perfect-forecast bound | Flood: past wx | Flood: **real issued forecasts** | Flood: bound |
|---|---|---|---|---|---|---|
| 6 h | −8% | **−38%** | −47% | −7% | **−37%** | −40% |
| 12 h | −5% | **−45%** | −57% | −4% | **−41%** | −51% |
| 24 h | −2% | **−44%** | −55% | −4% | **−48%** | −57% |

"Real issued forecasts" are Open-Meteo Previous-Runs archives of NWP forecasts issued about a day earlier. They're
used to both fit and score the model, so the test is valid in real time. For air, archived forecasts overlap only
~500 DEV hours, too few to test. Its past-weather gain is 4–7%.

## 2. TimesFM 2.5 (200M, PyTorch) zero-shot

The test uses 24-hour forecasts from rolling daily origins across TEST, with 1,024 hours of context.
"+xreg" adds TimesFM's in-context covariate mode, fed real issued weather forecasts.

| Idea | Model | MAE | MAPE | vs naive drift | vs best baseline | 80% PI coverage |
|---|---|---|---|---|---|---|
| Grid (146 origins) | **TimesFM+xreg** | **1,198 MW** | **4.6%** | +82% | **+39%** vs t−24h | — |
| | TimesFM | 1,232 MW | 4.8% | +82% | +37% | 73.6% |
| Flood (146) | **TimesFM** | **0.0112 m** | 5.8% | +31% | **+29%** vs persistence | 76.1% |
| | TimesFM+xreg | 0.0123 m | 6.8% | +24% | +22% | — |
| Air (30) | **TimesFM+xreg** | **7.0 µg/m³** | 26.8% | +51% | **+42%** vs t−168h | — |
| | TimesFM | 8.3 µg/m³ | 35.3% | +42% | +32% | 80.6% |

**Event windows** are the 20% of origins with the largest real rise in the next 24 hours, which is the moment
a warning system exists for:
- **Grid (30 windows):** TimesFM+xreg is best. Peak error is 1,392 MW, against 2,050 MW for the best baseline.
- **Flood (30 windows):** TimesFM alone is **no better than persistence** on surges. Peak error is 0.095 m against
  0.096 m, and it predicts flat lines. Its overall skill comes from calm periods. Adding real rain forecasts cuts
  peak error 19% (0.077 m) and shrinks the underestimate from −0.095 to −0.036 m.
- **Air (6 windows):** too few to conclude.

**Two bugs were found and fixed during the run, both of which would have reversed conclusions:**
- **TimesFM output slicing.** With `return_backcast=True`, the output starts with the reconstructed context. Taking
  the first 24 values made TimesFM look 18× worse than persistence.
- **Fit/score mismatch.** Fitting on actual weather and scoring on forecasts broke collinear coefficients and
  produced R² ≈ 0.

## 3. Verdict

| Rank | Idea | Call | Why |
|---|---|---|---|
| **1** | **GridPulse** | **GO** | Strongest and cleanest correlations (anomaly \|r\| 0.72–0.81). Weather-only out-of-sample R² 0.76. Real forecasts cut 6–24 h error ~40%. TimesFM+xreg reaches 4.6% MAPE and beats every baseline, including on demand peaks. Data is 100% complete with free, unlimited APIs. |
| 2 | FloodPulse | CONDITIONAL GO | Best physical story and impact. The correlations are real, and real rain forecasts cut 6–24 h error 37–48% in a linear model. But zero-shot TimesFM is surge-blind, and the evidence rests on one gauge and 30 test surges. Pursue it only with a rain-driven model, such as TimesFM+xreg with nonlinear rain features, validated on more gauges and winter storms. |
| 3 | AirPulse | NO-GO | No correlation reaches \|r\| 0.40. Weather-only R² is negative out of sample. Data gaps leave only 30 test origins. |

**Proceed with GridPulse.** Before building the app, run the honest benchmark: **NESO's own published day-ahead
demand forecast**, which is available through Elexon BMRS. The grid operator already forecasts demand well, so the
pitch has to show value it doesn't capture. Candidates are regional or embedded-solar demand anomalies, or
trading-relevant error in the operator's forecast, rather than only beating naive baselines. If that bar is too high,
FloodPulse has the more novel story, provided surge skill can be shown.

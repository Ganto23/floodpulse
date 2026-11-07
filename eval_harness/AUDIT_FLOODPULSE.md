# FloodPulse: hostile audit

Every finding was measured, not asserted. The audit scripts are `audit_forecast_lag.py` and `audit_lowflow.py`, plus
inline scans (reproducible from `data/rivers/*.csv`). Prediction dumps for 3 gauges are in `results/audit/`.

## 1. Hydrological and data anomalies

| Check | Finding | Evidence |
|---|---|---|
| Negative levels | **None** on any gauge (min 0.05 m on Cragg Brook; stage relative to local datum) | scan of all 10 gauges |
| Units (m vs mm) | **No mismatch.** Every gauge is in metres, with plausible ranges (Cragg 0.05–0.98 m, Derwent 0.44–2.82 m, Eden 0.44–6.02 m) | p01/p50/max per gauge |
| Stuck sensors (≥48 h flat) | **None** | run-length scan |
| Spikes (up >0.5 m/h and back within 2 h) | **1** (Calder-M). Ribble's 68 and Whalley's 26 >0.5 m/h jumps are sustained real rises | spike scan |
| Tidal contamination (Ribble) | **None:** no autocorrelation of Δlevel at the 12.42 h M2 period | ΔY autocorr |
| Datum shifts | **None found.** Aire's 0.53 m swing in yearly medians is seasonal sampling (2019 = Sep–Dec only); its low-flow p05 is stable at 0.29–0.38 m | yearly p05/p50 |
| Gaps | Calder-M has no data before 2022 (20,724 h gap); Greta stops in 2020; Whalley loses 3,551 h; Ribble 2,815 h; Eden 1,306 h. Gaps ≤6 h are interpolated for **inputs only**; targets are never filled | gap scan |
| **⚠ Spurious rain (tipping-bucket artifacts)** | **7 hours** of 33–74 mm/h with ERA5 ≈ 0 and no river response (Whalley Sep/Oct 2021, Derwent and Greta Aug 2022, **Calder-M 2024-09-10 = TEST**). The quality filter keeps everything except "Suspect"/"Missing" | `multi_river_fetch.py:64` |
| **⚠ Silent rain-source mixing** | Missing gauge rain falls back to ERA5 for **13.3% of hours (Aire)** and 6.7% (Wharfe). Gauge/ERA5 total ratio is 0.67–1.18, so the series mixes two scales | `floodpulse_stress.py:117` |

The fake 57.8 mm test-period spike **did not cause harm**: max over-prediction +0.11 m, peak forecast 1.58 m
against a P95 of 1.88 m, no warning. It's still a latent failure mode.

## 2. Model stability and boundary behaviour

**Low flow** (2024, 3 gauges, bias = prediction − actual):

| Regime | TimesFM | Booster | Comment |
|---|---|---|---|
| below P25 | +0.001…+0.003 m | +0.003…+0.007 m | tiny upward bias, by design (quantile loss q = 0.6) |
| P25–P75 | −0.003 m | +0.003…+0.016 m | negligible |
| surge > P95 | −0.27…−0.56 m | −0.02…−0.40 m | **both still under-predict surges** |

- **No flood-level false positives at low flow.** On no gauge or variant does the booster forecast above the P99
  threshold while the river is in its lower half.
- **⚠ Spurious surge forecasts with deployed rain.** The Kent gets **141** hour-forecasts above P95 while actually
  below median (Calder-M: 12). These are absent in the past-rain variant, so the cause is over-forecast rain hitting
  a booster trained on observed rain (train/serve skew, `floodpulse_stress.py:235`).

**NaN/Inf:**
- **Targets:** never filled; masked via `valid`.
- **Metrics guard their edge cases:** crest % is `None` when rise ≤ 0.05 m (`:317`); FAR is `None` with no warnings;
  surge MAE is `None` with no surge rows; the deployed variant drops rows lacking a full 24 h issued forecast.
- **Warnings** use `nanmax` over `-inf`-masked trajectories.
- **HGB quantile loss** can't produce Inf.
- **Residual risk:** `np.nanmean` of an empty slice → NaN in `mae_h`, which is written to JSON as `NaN`. Not hit in
  these runs.
- **Subtle:** forecasts are masked when the *target* is missing (`_trajectories`), so warning availability depends on
  future sensor uptime. Minor, but a selection effect.

## 3. Leakage and chronological integrity

| Item | Status | Measured impact |
|---|---|---|
| Scalers/thresholds (SSI percentile, P95, P99, empirical lag) | fit on TRAIN only (`:129`, `:134`). Phase 1 climatology and ridge standardization are DEV-only | ✓ none |
| HGB features | unscaled; no global statistics | ✓ |
| **⚠ Two-sided interpolation at the origin** | `interpolate(limit_area="inside")` fills gaps ≤6 h using readings *after* the origin (`floodpulse_stress.py:116`; `check_correlation.py:164`, ≤3 h) | **0.00% of test origins**, ≤0.05% of training origins: latent bug, zero effect |
| Train/test boundary | training origins on 31 Dec 2023 have 24 h targets inside 2024 (`:145`) | ~8 of ~12,000 origins: negligible |
| **⚠ Non-chronological storm tests** | Ciara (2020) and Babet (2023) are scored by boosters, SSI and thresholds fitted on 2019–2023, i.e. on years **after** the storm. The storms themselves are excluded ±7 days, so there's no test-data leakage, but it does use future-regime knowledge | not measured; a chronological Babet re-run is feasible |
| **⚠ Forecast issue time** | `_previous_day1` is "the value predicted 24 hours before valid time" (Open-Meteo docs), so it's always **issued** before the origin for h ≤ 24. Publication latency is undocumented (typically a few hours), so for h ≳ 20 h it may not have been **public** at the origin | Re-run with `_previous_day2` (48 h old, certainly public): Phase 1 median **−25% / −28% / −36%** vs **−32% / −43% / −45%**. Still positive at **9/9** gauges and every horizon (min −4%, Derwent 24 h) |
| ERA5 is not real-time | ERA5 has ~5 day latency, and its soil moisture comes from a reanalysis that assimilates observations around t (`:117`, `:129`) | not measured; the deployment answer is NWP-analysis soil moisture |
| TimesFM pretraining contamination | the corpus is undisclosed, so EA series can't be ruled out | unknowable |

## 4. Judge-facing vulnerabilities, ranked

| # | Severity | Vulnerability | Where | If asked |
|---|---|---|---|---|
| 1 | **High** | The headline relies on day-1 forecasts whose publication time is undocumented | `multi_river_fetch.py:114` | "With strictly-public 48 h-old forecasts, it's still −25…−36% at all 9 gauges. We quote −25…−45% as the range." |
| 2 | **High** | Storm results come from tiny samples | report Phase 2 | "Babet crest capture is 3/7 rivers (95% CI 16–75%). It's indicative only. 2024 warnings (61 events) are the firm number." |
| 3 | **High** | The baseline isn't the EA's operational forecast | Phase 1 | "Correct. We measure the value of rain information against river history, not against the EA. That comparison needs EA forecast archives, which aren't public." |
| 4 | **High** | Storm tests aren't chronological | `floodpulse_stress.py:145`, `:129`, `:134` | "No storm data was trained on, but later years were. Fix: retrain on data before 2023-10-10 for Babet." |
| 5 | Medium | Deployed booster is trained on observed rain | `:235` | "Train/serve skew. It explains the 46% catch rate and spurious surges. Fix: train on archived forecasts once ≥2 years exist." |
| 6 | Medium | Tipping-bucket artifacts pass QC | `multi_river_fetch.py:64` | "7 spurious hours found, 1 in test, with measured impact ≤0.11 m. Fix: drop gauge rain >25 mm/h when ERA5 and neighbouring gauges are dry." |
| 7 | Medium | Silent ERA5 fallback mixes rain sources | `floodpulse_stress.py:117` | "Up to 13% of hours. Fix: add a source-indicator feature or leave it missing." |
| 8 | Medium | The "perfect-forecast upper bound" isn't a strict bound (Calder-Whalley real −57% beats bound −53%) | `check_correlation.incremental`, `multi_river_phase1.py:30` | "The variants are fit on different training rows (forecast archive starts 2024). Fix: fit the oracle on the same rows." |
| 9 | Medium | The DEM lag ignores lakes (Derwent 4.3 h vs 39 h), so the arrival-rain feature is wrong there; Cragg's catchment snapped onto the Calder | `:137`, `elevation_features.py` | "Known physics gap: add FARL (lake attenuation) to Tc. Cragg's Tc falls back to its empirical lag." |
| 10 | Medium | Metric definitions are ours: θ = training P99, not EA flood thresholds; FAR is per hourly forecast, not per event; capture tolerance ±20% / ±3 h | `:134`, `:353`, `:319` | "Stated in the report. Next: EA flood-alert thresholds and event-based FAR." |
| 11 | Low | "Mean error reduction" is actually a median | `floodpulse_report.py:89` | label corrected in the report |
| 12 | Low | Two-sided interpolation and boundary overlap | `:116`, `:145`, `check_correlation.py:164` | "Measured at 0.00% of test origins. Fix: forward-fill only, and require o + H < test start." |
| 13 | Low | TimesFM may have seen these series in pretraining | — | "Can't be ruled out. The booster and ablations are evaluated relative to TimesFM, so contamination would flatter the baseline, not our gains." |

**Net:** no finding reverses a headline result. Two change how they should be stated:
- the forecast error reduction becomes **−25…−45%** (not −32…−45%);
- storm crest capture is **indicative only**.

The biggest real weakness is still that warning lead time with deployed forecasts is ~2 h.

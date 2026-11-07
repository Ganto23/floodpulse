# GridPulse: Can weather predict NESO's demand forecast errors?

**Data:** 2024-03-01 → 2024-12-31, hourly, 7,344 h, 100% coverage on every source.
- Elexon INDO outturn, plus the full NESO NDF publication log (14,778 publications, 866k rows).
- Open-Meteo ERA5 weather and archived issued NWP forecasts, averaged over 5 cities.

**Definitions:**
- **Day-ahead** = latest NDF published by 10:00 UTC on D-1 (day-ahead auction gate; 14–37.5 h lead).
- **Residual** = INDO − day-ahead NDF.
- **Split:** DEV is Mar–Sep; TEST is Oct–Dec (2,204 h).

**Reproduce:** `fetch_residuals.py` → `check_residuals.py` → `test_timesfm_residuals.py`.

## Summary

| Metric | Value |
|---|---|
| **NESO day-ahead MAE** | **615 MW (2.45%)**, RMSE 821, bias +17 MW |
| NESO's own update, ≥1 h before | 459 MW (1.84%). NESO already removes 25% of its day-ahead error |
| **Peak weather-volatility correlation with \|NESO error\|** | raw r = +0.25 (Δtemp 3 h), but only **+0.05 after removing hour of day**. Every feature is \|r\| ≤ 0.13 after adjustment |
| Top-10% error events coinciding with large weather moves | solar surprise 30% vs 16.5% base rate (**1.84× lift**). All other flags 0.65–1.27× |
| **Directional capture from weather** | **48–53%** (coin flip; majority class 51.8%) |
| Directional capture, best model (error persistence) | 77% at 1 h, **90.6% on larger errors** |
| Best model vs NESO's latest forecast | **+16.9% at 1 h**, +6.8% at 3 h, +4.5% at 6 h; only +7.3% at 1 h with 1 h more data latency |
| TimesFM zero-shot on residuals | +5.2% vs NESO's latest at 1 h; worse at 3–6 h. Weather covariates add ≤0.5 pp |

## Ablation (TEST, 1 h lead, MAE of corrected forecast)

| Model | MAE (MW) | vs NESO latest | Direction |
|---|---|---|---|
| ridge, **no weather** (residual lags + NESO revision + hour) | **381** | **+16.9%** | 77.0% |
| ridge, all features | 382 | +16.7% | 76.8% |
| ridge, all features, +1 h latency | 425 | +7.3% | 73.0% |
| TimesFM + weather covariates | 433 | +5.7% | 73.9% |
| TimesFM | 434 | +5.2% | 73.3% |
| NESO latest (≥1 h before) | 458 | 0 | 72.2% |
| ridge, **weather only** | 623 | −35.9% | 52.7% |

## Verdict: NO-GO on the hypothesis as stated

**Claim tested:** "NESO systematically errs during weather shifts, and weather + TimesFM predicts the error."
- **Not supported.** Once the clock is controlled for, weather volatility and weather surprise have almost no
  relationship with NESO's errors. Weather features add nothing to the residual model and can't call the direction.
- **The one weather signal is weak:** large solar surprises are 1.84× over-represented in big-error hours. That's
  too little to predict on alone.

**What is real:** NESO's errors persist from hour to hour. A simple model using recent errors and NESO's own
revisions beats NESO's latest published forecast by 7–17% one hour ahead, and calls direction ~75–90%. But:
- **The edge depends on data latency.** It needs outturn data within the hour; one extra hour of delay halves it.
  It fades by 6 hours.
- **It's a nowcast, not weather alt-data.** It's useful for intraday/balancing positions, which is a
  different (and narrower) product than the GridPulse pitch.

**Caveats that could change this:**
- **Weather is coarse.** It's an unweighted 5-city average from ERA5 and a different NWP model from the one NESO uses.
  Regional solar weighting (capacity is concentrated in the South) is the one untested idea with a physical basis.
  It should be pre-registered before testing, not fished for.
- **One test season:** Oct–Dec 2024.

**Dashboard recommendation:** don't build the weather-driven GridPulse dashboard. If you pursue anything here, the
defensible product is "1-hour NESO error nowcast from error persistence". First verify real INDO publication latency,
since the whole edge depends on it.

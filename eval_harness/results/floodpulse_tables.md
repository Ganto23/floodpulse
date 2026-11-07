## Phase 1

| Gauge | Best feature (r, lag) | Real fc 6 h | 12 h | 24 h | Perfect-fc bound 24 h | R² 24 h: AR → +weather |
|---|---|---|---|---|---|---|
| calder_mytholmroyd | soil_moisture_7_to_28cm (+0.64, 1 h) | −37% | −44% | −50% | −61% | 0.12 → 0.56 |
| cragg_dauber_bridge | soil_moisture_7_to_28cm (+0.67, 1 h) | −35% | −38% | −45% | −56% | 0.38 → 0.66 |
| aire_armley | soil_moisture_7_to_28cm (+0.68, 1 h) | −22% | −30% | −42% | −55% | 0.45 → 0.68 |
| calder_whalley | precip_24h (+0.73, 1 h) | −42% | −56% | −57% | −53% | 0.13 → 0.63 |
| eden_sheepmount | soil_moisture_7_to_28cm (+0.67, 6 h) | −31% | −43% | −41% | −72% | 0.37 → 0.63 |
| greta_low_briery | excluded: no level data after 2020 | | | | | |
| wharfe_otley | soil_moisture_7_to_28cm (+0.58, 4 h) | −27% | −34% | −43% | −49% | 0.07 → 0.47 |
| ribble_samlesbury | precip_24h (+0.71, 5 h) | −32% | −51% | −57% | −60% | 0.13 → 0.62 |
| kent_victoria_bridge | precip_24h (+0.71, 1 h) | −52% | −54% | −54% | −80% | 0.24 → 0.65 |
| derwent_ouse_bridge | soil_moisture_7_to_28cm (+0.66, 25 h) | −25% | −28% | −19% | −69% | 0.95 → 0.96 |
| **median (n=9)** | | **−32%** | **−43%** | **−45%** | | |

## DEM

| Gauge | DEM area km² | NRFA area km² | ratio | Longest path km | Relief m | Kirpich Tc h | Empirical rain→peak lag h |
|---|---|---|---|---|---|---|---|
| calder_mytholmroyd | 144.2 | 141.87 | 1.02 | 15.8 | 362 | 2.4 | 4 |
| cragg_dauber_bridge ⚠ snapped to Calder | 156.2 | — | — | 19.2 | 383 | 2.9 | 5 |
| aire_armley | 691.4 | 691.5 | 1.00 | 66.6 | 476 | 11.3 | 10 |
| calder_whalley | 316.8 | 316.0 | 1.00 | 31.7 | 483 | 4.8 | 5 |
| eden_sheepmount | 2190.2 | 2286.5 | 0.96 | 92.5 | 780 | 13.6 | 17 |
| greta_low_briery | 139.9 | 145.6 | 0.96 | 22.6 | 804 | 2.6 | 5 |
| wharfe_otley | 539.7 | — | — | 66.3 | 640 | 10.0 | 11 |
| ribble_samlesbury | 946.1 | 1145.0 | 0.83 | 63.5 | 563 | 10.0 | 10 |
| kent_victoria_bridge | 186.4 | 183.0 | 1.02 | 22.1 | 730 | 2.7 | 6 |
| derwent_ouse_bridge | 359.6 | 363.0 | 0.99 | 34.3 | 820 | 4.3 | 39 |

## Accuracy

**2024 · deployed**

| Gauge | Persistence MAE / surge MAE (bias) | TimesFM MAE / surge MAE (bias) | TimesFM+booster (no physics) MAE / surge MAE (bias) | TimesFM+booster (physics) MAE / surge MAE (bias) |
|---|---|---|---|---|
| aire_armley | 0.088 / 0.608 (-0.456) | 0.069 / 0.618 (-0.534) | 0.056 / 0.343 (-0.288) | 0.056 / 0.341 (-0.289) |
| calder_mytholmroyd | 0.053 / 0.650 (-0.434) | 0.043 / 0.644 (-0.561) | 0.033 / 0.372 (-0.292) | 0.032 / 0.353 (-0.285) |
| calder_whalley | 0.084 / 0.885 (-0.628) | 0.065 / 0.888 (-0.777) | 0.048 / 0.482 (-0.381) | 0.047 / 0.456 (-0.360) |
| cragg_dauber_bridge | 0.016 / 0.170 (-0.141) | 0.013 / 0.174 (-0.164) | 0.010 / 0.099 (-0.086) | 0.010 / 0.095 (-0.076) |
| derwent_ouse_bridge | 0.032 / 0.075 (-0.019) | 0.018 / 0.055 (-0.006) | 0.011 / 0.040 (-0.034) | 0.012 / 0.041 (-0.032) |
| eden_sheepmount | 0.122 / 0.946 (-0.685) | 0.093 / 0.924 (-0.749) | 0.072 / 0.556 (-0.403) | 0.072 / 0.521 (-0.331) |
| kent_victoria_bridge | 0.048 / 0.289 (-0.221) | 0.037 / 0.305 (-0.271) | 0.026 / 0.175 (-0.123) | 0.026 / 0.171 (-0.118) |
| ribble_samlesbury | 0.150 / 1.090 (-0.854) | 0.111 / 1.074 (-0.937) | 0.081 / 0.547 (-0.406) | 0.078 / 0.538 (-0.397) |
| wharfe_otley | 0.030 / 0.226 (-0.170) | 0.024 / 0.231 (-0.200) | 0.023 / 0.153 (-0.122) | 0.022 / 0.152 (-0.108) |

**2024 · oracle**

| Gauge | Persistence MAE / surge MAE (bias) | TimesFM MAE / surge MAE (bias) | TimesFM+booster (no physics) MAE / surge MAE (bias) | TimesFM+booster (physics) MAE / surge MAE (bias) |
|---|---|---|---|---|
| aire_armley | 0.095 / 0.490 (-0.292) | 0.073 / 0.462 (-0.347) | 0.051 / 0.253 (-0.164) | 0.050 / 0.243 (-0.173) |
| calder_mytholmroyd | 0.059 / 0.574 (-0.367) | 0.047 / 0.554 (-0.476) | 0.030 / 0.258 (-0.123) | 0.028 / 0.221 (-0.109) |
| calder_whalley | 0.093 / 0.795 (-0.563) | 0.071 / 0.787 (-0.691) | 0.040 / 0.334 (-0.200) | 0.037 / 0.288 (-0.136) |
| cragg_dauber_bridge | 0.018 / 0.155 (-0.119) | 0.015 / 0.153 (-0.139) | 0.009 / 0.058 (-0.029) | 0.009 / 0.052 (-0.019) |
| derwent_ouse_bridge | 0.035 / 0.079 (-0.021) | 0.019 / 0.060 (+0.011) | 0.011 / 0.030 (+0.004) | 0.011 / 0.029 (+0.008) |
| eden_sheepmount | 0.137 / 0.872 (-0.552) | 0.105 / 0.825 (-0.583) | 0.073 / 0.507 (-0.347) | 0.071 / 0.479 (-0.297) |
| kent_victoria_bridge | 0.052 / 0.295 (-0.211) | 0.041 / 0.302 (-0.262) | 0.022 / 0.118 (-0.033) | 0.021 / 0.113 (-0.024) |
| ribble_samlesbury | 0.166 / 1.033 (-0.755) | 0.122 / 1.005 (-0.861) | 0.077 / 0.429 (-0.255) | 0.070 / 0.382 (-0.210) |
| wharfe_otley | 0.035 / 0.233 (-0.140) | 0.027 / 0.226 (-0.175) | 0.024 / 0.163 (-0.116) | 0.024 / 0.160 (-0.112) |

**2024 · past**

| Gauge | Persistence MAE / surge MAE (bias) | TimesFM MAE / surge MAE (bias) | TimesFM+booster (no physics) MAE / surge MAE (bias) | TimesFM+booster (physics) MAE / surge MAE (bias) |
|---|---|---|---|---|
| aire_armley | 0.095 / 0.490 (-0.292) | 0.073 / 0.462 (-0.347) | 0.071 / 0.391 (-0.290) | 0.069 / 0.380 (-0.282) |
| calder_mytholmroyd | 0.059 / 0.574 (-0.367) | 0.047 / 0.554 (-0.476) | 0.051 / 0.495 (-0.402) | 0.049 / 0.493 (-0.403) |
| calder_whalley | 0.093 / 0.795 (-0.563) | 0.071 / 0.787 (-0.691) | 0.067 / 0.679 (-0.607) | 0.067 / 0.682 (-0.602) |
| cragg_dauber_bridge | 0.018 / 0.155 (-0.119) | 0.015 / 0.153 (-0.139) | 0.014 / 0.132 (-0.121) | 0.015 / 0.132 (-0.121) |
| derwent_ouse_bridge | 0.035 / 0.079 (-0.021) | 0.019 / 0.060 (+0.011) | 0.014 / 0.039 (-0.006) | 0.015 / 0.039 (-0.004) |
| eden_sheepmount | 0.137 / 0.872 (-0.552) | 0.105 / 0.825 (-0.583) | 0.087 / 0.621 (-0.451) | 0.088 / 0.626 (-0.430) |
| kent_victoria_bridge | 0.052 / 0.295 (-0.211) | 0.041 / 0.302 (-0.262) | 0.037 / 0.262 (-0.228) | 0.037 / 0.263 (-0.224) |
| ribble_samlesbury | 0.166 / 1.033 (-0.755) | 0.122 / 1.005 (-0.861) | 0.102 / 0.754 (-0.632) | 0.102 / 0.760 (-0.622) |
| wharfe_otley | 0.035 / 0.233 (-0.140) | 0.027 / 0.226 (-0.175) | 0.026 / 0.191 (-0.154) | 0.026 / 0.191 (-0.154) |

## Storms

**ciara_dennis · past**  (peak error as % of the rise from origin to crest; timing error h; ✓ = within ±20% and ±3 h)

| Gauge | crest m | lead | Persistence | TimesFM | TimesFM+booster (no physics) | TimesFM+booster (physics) |
|---|---|---|---|---|---|---|
| aire_armley | 4.13 | 6 h | -100%, -5 h | -93%, -4 h | -95%, -5 h | -89%, -4 h |
| aire_armley | 4.13 | 12 h | -100%, -11 h | -94%, -10 h | -76%, -7 h | -76%, -6 h |
| cragg_dauber_bridge | 0.98 | 6 h | -100%, -5 h | -95%, -4 h | -81%, -3 h | -83%, -3 h |
| cragg_dauber_bridge | 0.98 | 12 h | -100%, -11 h | -99%, +11 h | -91%, +2 h | -89%, +2 h |
| derwent_ouse_bridge | 2.73 | 12 h | -100%, -11 h | +140%, +11 h | -7%, +11 h | -13%, -5 h |
| eden_sheepmount | 6.02 | 6 h | -100%, -5 h | -69%, -2 h | -72%, -1 h | -70%, -2 h |
| eden_sheepmount | 6.02 | 12 h | -100%, -11 h | -86%, -8 h | -69%, +1 h | -70%, -3 h |
| greta_low_briery | 2.34 | 6 h | -100%, -5 h | -80%, -2 h | -55%, -2 h | -38%, -2 h |
| greta_low_briery | 2.34 | 12 h | -100%, -11 h | -97%, -11 h | -93%, -11 h | -84%, -11 h |
| kent_victoria_bridge | 2.93 | 6 h | -100%, -5 h | -53%, -1 h | -42%, -1 h | -49%, -2 h |
| kent_victoria_bridge | 2.93 | 12 h | -100%, -11 h | -101%, -11 h | -101%, -11 h | -101%, -11 h |
| wharfe_otley | 1.92 | 6 h | -100%, -5 h | -88%, -4 h | -74%, -3 h | -70%, -3 h |
| wharfe_otley | 1.92 | 12 h | -100%, -11 h | -97%, -10 h | -78%, -3 h | -75%, -3 h |

**ciara_dennis · oracle**  (peak error as % of the rise from origin to crest; timing error h; ✓ = within ±20% and ±3 h)

| Gauge | crest m | lead | Persistence | TimesFM | TimesFM+booster (no physics) | TimesFM+booster (physics) |
|---|---|---|---|---|---|---|
| aire_armley | 4.13 | 6 h | -100%, -5 h | -93%, -4 h | -89%, -5 h | -118%, -5 h |
| aire_armley | 4.13 | 12 h | -100%, -11 h | -94%, -10 h | -42%, -5 h | -40%, -2 h |
| cragg_dauber_bridge | 0.98 | 6 h | -100%, -5 h | -95%, -4 h | -54%, +0 h | -55%, +0 h |
| cragg_dauber_bridge | 0.98 | 12 h | -100%, -11 h | -99%, +11 h | -57%, -2 h | -56%, +5 h |
| derwent_ouse_bridge | 2.73 | 12 h | -100%, -11 h | +140%, +11 h | +53%, +7 h | +2%, +4 h |
| eden_sheepmount | 6.02 | 6 h | -100%, -5 h | -69%, -2 h | -67%, -2 h | -68%, +0 h |
| eden_sheepmount | 6.02 | 12 h | -100%, -11 h | -86%, -8 h | -70%, -2 h | -65%, -2 h |
| greta_low_briery | 2.34 | 6 h | -100%, -5 h | -80%, -2 h | +65%, -2 h | +63%, -2 h |
| greta_low_briery | 2.34 | 12 h | -100%, -11 h | -97%, -11 h | -80%, -10 h | -74%, -8 h |
| kent_victoria_bridge | 2.93 | 6 h | -100%, -5 h | -53%, -1 h | -14%, -1 h ✓ | -9%, -1 h ✓ |
| kent_victoria_bridge | 2.93 | 12 h | -100%, -11 h | -101%, -11 h | -51%, +0 h | -46%, -2 h |
| wharfe_otley | 1.92 | 6 h | -100%, -5 h | -88%, -4 h | -58%, -3 h | -53%, -2 h |
| wharfe_otley | 1.92 | 12 h | -100%, -11 h | -97%, -10 h | -63%, -3 h | -62%, -3 h |

**babet · past**  (peak error as % of the rise from origin to crest; timing error h; ✓ = within ±20% and ±3 h)

| Gauge | crest m | lead | Persistence | TimesFM | TimesFM+booster (no physics) | TimesFM+booster (physics) |
|---|---|---|---|---|---|---|
| aire_armley | 3.63 | 6 h | -100%, -5 h | -64%, -4 h | -40%, -1 h | -59%, -4 h |
| aire_armley | 3.63 | 12 h | -100%, -11 h | -93%, -11 h | -86%, -8 h | -79%, -8 h |
| calder_mytholmroyd | 3.19 | 6 h | -100%, -5 h | -101%, -5 h | -82%, -4 h | -68%, -4 h |
| calder_mytholmroyd | 3.19 | 12 h | -100%, -11 h | -85%, -8 h | -68%, -8 h | -74%, -8 h |
| calder_whalley | 2.11 | 6 h | -100%, -5 h | -82%, +0 h | -50%, -1 h | -35%, +0 h |
| calder_whalley | 2.11 | 12 h | -100%, -11 h | -99%, -8 h | -100%, -11 h | -99%, -9 h |
| cragg_dauber_bridge | 0.75 | 6 h | -100%, -5 h | -94%, -5 h | -82%, -4 h | -91%, -4 h |
| cragg_dauber_bridge | 0.75 | 12 h | -100%, -11 h | -97%, -8 h | -76%, -7 h | -74%, -9 h |
| eden_sheepmount | 2.01 | 6 h | -100%, -5 h | -13%, +3 h ✓ | -62%, -2 h | -80%, -2 h |
| eden_sheepmount | 2.01 | 12 h | -100%, -11 h | -45%, -3 h | -67%, -6 h | -75%, -5 h |
| kent_victoria_bridge | 1.41 | 12 h | -100%, -11 h | -92%, -4 h | +55%, -5 h | +66%, -3 h |
| wharfe_otley | 1.18 | 6 h | -100%, -5 h | -50%, -3 h | -24%, +0 h | -10%, -2 h ✓ |
| wharfe_otley | 1.18 | 12 h | -100%, -11 h | -93%, -8 h | -61%, -4 h | -49%, -5 h |

**babet · oracle**  (peak error as % of the rise from origin to crest; timing error h; ✓ = within ±20% and ±3 h)

| Gauge | crest m | lead | Persistence | TimesFM | TimesFM+booster (no physics) | TimesFM+booster (physics) |
|---|---|---|---|---|---|---|
| aire_armley | 3.63 | 6 h | -100%, -5 h | -64%, -4 h | +30%, +0 h | -33%, +1 h |
| aire_armley | 3.63 | 12 h | -100%, -11 h | -93%, -11 h | -9%, -4 h | +5%, -1 h ✓ |
| calder_mytholmroyd | 3.19 | 6 h | -100%, -5 h | -101%, -5 h | -56%, -3 h | -54%, +0 h |
| calder_mytholmroyd | 3.19 | 12 h | -100%, -11 h | -85%, -8 h | -20%, -4 h | -1%, -1 h ✓ |
| calder_whalley | 2.11 | 6 h | -100%, -5 h | -82%, +0 h | -40%, +1 h | -28%, +3 h |
| calder_whalley | 2.11 | 12 h | -100%, -11 h | -99%, -8 h | -39%, +3 h | -21%, -1 h |
| cragg_dauber_bridge | 0.75 | 6 h | -100%, -5 h | -94%, -5 h | -29%, +2 h | -39%, +2 h |
| cragg_dauber_bridge | 0.75 | 12 h | -100%, -11 h | -97%, -8 h | -32%, -4 h | -30%, -1 h |
| eden_sheepmount | 2.01 | 6 h | -100%, -5 h | -13%, +3 h ✓ | -48%, +0 h | -69%, -3 h |
| eden_sheepmount | 2.01 | 12 h | -100%, -11 h | -45%, -3 h | -66%, -6 h | -69%, -5 h |
| kent_victoria_bridge | 1.41 | 12 h | -100%, -11 h | -92%, -4 h | -6%, -5 h | -8%, -1 h ✓ |
| wharfe_otley | 1.18 | 6 h | -100%, -5 h | -50%, -3 h | +41%, +3 h | -31%, +2 h |
| wharfe_otley | 1.18 | 12 h | -100%, -11 h | -93%, -8 h | -22%, -2 h | -26%, -1 h |


## Warnings

| Test set · variant | events | Persistence: hit / mean lead h / FAR | TimesFM: hit / mean lead h / FAR | TimesFM+booster (no physics): hit / mean lead h / FAR | TimesFM+booster (physics): hit / mean lead h / FAR |
|---|---|---|---|---|---|
| 2024 · deployed | 61 | 0% / 0.0 / 0.11 | 31% / 0.4 / 0.08 | 38% / 0.8 / 0.12 | 46% / 1.7 / 0.17 |
| 2024 · oracle | 61 | 0% / 0.0 / 0.11 | 66% / 1.0 / 0.14 | 75% / 4.0 / 0.21 | 79% / 5.4 / 0.26 |
| 2024 · past | 61 | 0% / 0.0 / 0.11 | 66% / 1.0 / 0.14 | 72% / 1.7 / 0.16 | 79% / 2.1 / 0.17 |
| ciara_dennis · oracle | 25 | 0% / 0.0 / 0.03 | 92% / 2.1 / 0.03 | 100% / 11.4 / 0.01 | 100% / 15.4 / 0.01 |
| ciara_dennis · past | 25 | 0% / 0.0 / 0.03 | 92% / 2.1 / 0.03 | 100% / 2.6 / 0.02 | 100% / 3.0 / 0.02 |
| babet · oracle | 5 | 0% / 0.0 / 0.06 | 80% / 1.0 / 0.01 | 100% / 11.4 / 0.01 | 100% / 13.8 / 0.01 |
| babet · past | 5 | 0% / 0.0 / 0.06 | 80% / 1.0 / 0.01 | 100% / 1.2 / 0.00 | 80% / 1.4 / 0.03 |

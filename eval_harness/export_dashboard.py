"""
Export REAL FloodPulse backtest outputs for the dashboard (floodpulse-ui/public/data). No synthetic values.

Inputs   results/dashboard/<gauge>_<set>_<variant>.npz  (floodpulse_stress.py with FP_DUMP)
         results/dashboard/<gauge>.json, data/rivers/{stations,catchments,phase1,audit_forecast_lag}.json,
         data/rivers/geometry/<gauge>.json, results/floodpulse_summary.json
Outputs  manifest.json                 gauges, thresholds, audited headline metrics, set definitions
         status_<set>_<variant>.json   per replay time × gauge: observed, FloodPulse peak within 6/12/18/24 h,
                                       first hour the forecast reaches the P99 threshold (breach window)
         gauge_<slug>.json             observed hourly levels + forecast trajectories at replay times
         geometry_<slug>.json          DEM catchment mesh + D8 channel segments
Levels are integer millimetres. FloodPulse band = TimesFM q10–q90 shifted by the booster correction
(an approximation: the booster itself is a q=0.6 point model).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
RIV = ROOT / "data" / "rivers"
DUMP = ROOT / "results" / "dashboard"
OUT = ROOT.parent / "floodpulse-ui" / "public" / "data"
H = 24
SETS = {"2024": {"label": "2024 backtest", "variants": ["deployed", "oracle", "past"], "step": 3},
        "ciara_dennis": {"label": "Storm Ciara/Dennis · Feb 2020", "variants": ["past", "oracle"], "step": 1},
        "babet": {"label": "Storm Babet · Oct 2023", "variants": ["past", "oracle"], "step": 1}}
VARIANT_LABEL = {"deployed": "Real issued forecasts", "oracle": "Perfect rain forecast (upper bound)",
                 "past": "Past rain only"}
NAMES = {"calder_mytholmroyd": "Calder · Mytholmroyd", "cragg_dauber_bridge": "Cragg Brook · Mytholmroyd",
         "aire_armley": "Aire · Armley (Leeds)", "calder_whalley": "Calder · Whalley Weir",
         "eden_sheepmount": "Eden · Sheepmount (Carlisle)", "greta_low_briery": "Greta · Low Briery (Keswick)",
         "wharfe_otley": "Wharfe · Otley", "ribble_samlesbury": "Ribble · Samlesbury",
         "kent_victoria_bridge": "Kent · Victoria Bridge (Kendal)", "derwent_ouse_bridge": "Derwent · Ouse Bridge"}
mm = lambda a: [None if not np.isfinite(x) else int(round(x * 1000)) for x in np.asarray(a, float)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stations = json.loads((RIV / "stations.json").read_text())
    catch = json.loads((RIV / "catchments.json").read_text())
    phase1 = {r["gauge"]: r for r in json.loads((RIV / "phase1.json").read_text())["rows"]}
    lag_audit = {r["gauge"]: r for r in json.loads((RIV / "audit_forecast_lag.json").read_text())}
    summary = json.loads((ROOT / "results" / "floodpulse_summary.json").read_text())

    gauges, status = [], {}
    for slug, st in stations.items():
        res_p = DUMP / f"{slug}.json"
        if not res_p.exists():
            continue
        res = json.loads(res_p.read_text())
        if "sets" not in res:
            continue
        df = pd.read_csv(RIV / f"{slug}.csv", index_col="time", parse_dates=True)
        idx = df.index
        y = df["y"].to_numpy()
        g = {"slug": slug, "name": NAMES.get(slug, slug), "river": st["river"], "lat": st["lat"], "lon": st["lon"],
             "p95_mm": int(round(res["p95"] * 1000)), "p99_mm": int(round(res["p99_threshold"] * 1000)),
             "dem_tc_h": catch[slug]["kirpich_tc_h"], "empirical_lag_h": res["empirical_lag"]["to_peak"]["lag_h"],
             "dem_area_km2": catch[slug]["dem_area_km2"], "nrfa_area_km2": catch[slug]["nrfa_area_km2"],
             "dem_unreliable": slug == "cragg_dauber_bridge",
             "phase1": ({h: {"day1": phase1[slug][f"real_fc_{h}h"], "day2": lag_audit.get(slug, {}).get(f"d2_{h}")}
                         for h in (6, 12, 24)} if slug in phase1 and "real_fc_6h" in phase1[slug] else None),
             "sets": {}}
        payload = {"slug": slug, "sets": {}}
        for set_name, spec in SETS.items():
            if set_name not in res["sets"]:
                continue
            obs_mask = None
            set_payload = {"variants": {}}
            for var in spec["variants"]:
                p = DUMP / f"{slug}_{set_name}_{var}.npz"
                if not p.exists():
                    continue
                d = np.load(p)
                o, h = d["o"], d["h"]
                origins = np.unique(o)[::spec["step"]]
                pos = {x: i for i, x in enumerate(np.unique(o))}
                n_all = len(pos)
                shape = (n_all, H)
                arr = {k: np.full(shape, np.nan) for k in ("timesfm", "booster", "tfm_q10", "tfm_q90")}
                rows = np.array([pos[x] for x in o])
                valid = d["valid"]
                for k in arr:
                    arr[k][rows, h - 1] = np.where(valid, d[k], np.nan)
                keep = np.array([pos[x] for x in origins])
                corr = arr["booster"] - arr["timesfm"]
                lo, hi = arr["tfm_q10"] + corr, arr["tfm_q90"] + corr
                set_payload["variants"][var] = {
                    "origins": [str(idx[x]) for x in origins],
                    "baseline": [mm(arr["timesfm"][i]) for i in keep],
                    "floodpulse": [mm(arr["booster"][i]) for i in keep],
                    "band_lo": [mm(lo[i]) for i in keep], "band_hi": [mm(hi[i]) for i in keep],
                }
                # status rows for the map / sidebar
                srows = status.setdefault((set_name, var), {})
                thr = res["p99_threshold"]
                for i_k, x in zip(keep, origins):
                    tr = arr["booster"][i_k]
                    peaks = {hz: (None if not np.isfinite(tr[:hz]).any() else int(round(np.nanmax(tr[:hz]) * 1000)))
                             for hz in (6, 12, 18, 24)}
                    hit = np.where(np.nan_to_num(tr, nan=-1e9) >= thr)[0]
                    srows.setdefault(str(idx[x]), {})[slug] = {
                        "obs": mm([y[x]])[0], "peak": peaks, "breach_h": int(hit[0] + 1) if len(hit) else None}
                if obs_mask is None:
                    lo_i, hi_i = max(0, origins.min() - 72), min(len(idx) - 1, origins.max() + H)
                    obs_mask = (lo_i, hi_i)
            if obs_mask:
                a, b = obs_mask
                set_payload["obs_start"] = str(idx[a])
                set_payload["obs"] = mm(y[a:b + 1])
                payload["sets"][set_name] = set_payload
                v = res["sets"][set_name]["variants"]
                g["sets"][set_name] = {
                    var: {"mae_mm": {m: round(v[var][m]["mae"] * 1000, 1) for m in ("persistence", "timesfm", "booster")},
                          "surge_mae_mm": {m: (round(v[var][m]["surge_mae"] * 1000, 1) if v[var][m]["surge_mae"] else None)
                                           for m in ("persistence", "timesfm", "booster")},
                          "warning": {m: v[var]["warning"]["models"][m] for m in ("timesfm", "booster")},
                          "events": v[var]["warning"]["events"],
                          "crest": v[var].get("crest")}
                    for var in v}
        (OUT / f"gauge_{slug}.json").write_text(json.dumps(payload, separators=(",", ":")))
        geo = RIV / "geometry" / f"{slug}.json"
        if geo.exists():
            shutil.copy(geo, OUT / f"geometry_{slug}.json")
        gauges.append(g)
        print(f"exported {slug}: sets {list(payload['sets'])}")

    for (set_name, var), rows in status.items():
        times = sorted(rows)
        (OUT / f"status_{set_name}_{var}.json").write_text(json.dumps(
            {"times": times, "rows": [rows[t] for t in times]}, separators=(",", ":")))

    w = summary["warnings"]
    manifest = {
        "generated": pd.Timestamp.now(tz="UTC").isoformat(),
        "mode": "BACKTEST REPLAY — retrospective evaluation, not live telemetry",
        "sets": {k: {"label": v["label"], "variants": v["variants"]} for k, v in SETS.items()},
        "variant_labels": VARIANT_LABEL,
        "headline": {
            "error_reduction_day1": {str(h): summary["phase1"][str(h)] for h in (6, 12, 24)},
            "error_reduction_day2": {str(h): float(np.median([r[f"d2_{h}"] for r in lag_audit.values()])) for h in (6, 12, 24)},
            "booster_deployed": summary["accuracy"]["2024_deployed"],
            "warnings_2024_deployed": w["2024_deployed"], "warnings_2024_oracle": w["2024_oracle"],
            "warnings_ciara_oracle": w.get("ciara_dennis_oracle"), "warnings_babet_oracle": w.get("babet_oracle"),
            "dem_lag": summary["dem_lag"], "storms": summary["storms"],
            "gauges_phase1": summary["phase1"]["n"],
        },
        "gauges": gauges,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    print(f"manifest: {len(gauges)} gauges → {OUT}")


if __name__ == "__main__":
    main()

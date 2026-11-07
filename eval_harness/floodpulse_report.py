"""Compile results/floodpulse/*.json + phase1 + catchments into tables (markdown) for the final report."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).parent
RIV = ROOT / "data" / "rivers"
RES = ROOT / "results" / "floodpulse"
M = ("persistence", "timesfm", "booster_nophys", "booster")
MN = {"persistence": "Persistence", "timesfm": "TimesFM", "booster_nophys": "TimesFM+booster (no physics)",
      "booster": "TimesFM+booster (physics)"}
f = lambda x, s="{:.3f}": "—" if x is None or (isinstance(x, float) and np.isnan(x)) else s.format(x)


def load():
    out = {}
    for p in sorted(RES.glob("*.json")):
        r = json.loads(p.read_text())
        if "sets" in r:
            out[r["gauge"]] = r
    return out


def phase1_table() -> tuple[str, dict]:
    rows = json.loads((RIV / "phase1.json").read_text())["rows"]
    lines = ["| Gauge | Best feature (r, lag) | Real fc 6 h | 12 h | 24 h | Perfect-fc bound 24 h | R² 24 h: AR → +weather |",
             "|---|---|---|---|---|---|---|"]
    ok = []
    for r in rows:
        if "excluded" in r:
            lines.append(f"| {r['gauge']} | excluded: {r['excluded']} | | | | | |"); continue
        ok.append(r)
        lines.append(f"| {r['gauge']} | {r['best_feature']} ({r['best_r']:+.2f}, {r['best_lag']} h) | "
                     f"−{r['real_fc_6h']:.0%} | −{r['real_fc_12h']:.0%} | −{r['real_fc_24h']:.0%} | −{r['oracle_24h']:.0%} | "
                     f"{r['r2_ar_24h']:.2f} → {r['r2_arx_24h']:.2f} |")
    agg = {h: float(np.median([r[f"real_fc_{h}h"] for r in ok])) for h in (6, 12, 24)}
    agg["n"] = len(ok)
    agg["min24"] = float(min(r["real_fc_24h"] for r in ok))
    agg["max24"] = float(max(r["real_fc_24h"] for r in ok))
    lines.append(f"| **median (n={len(ok)})** | | **−{agg[6]:.0%}** | **−{agg[12]:.0%}** | **−{agg[24]:.0%}** | | |")
    return "\n".join(lines), agg


def dem_table(res) -> tuple[str, dict]:
    c = json.loads((RIV / "catchments.json").read_text())
    lines = ["| Gauge | DEM area km² | NRFA area km² | ratio | Longest path km | Relief m | Kirpich Tc h | Empirical rain→peak lag h |",
             "|---|---|---|---|---|---|---|---|"]
    tc, emp = [], []
    for g, d in c.items():
        e = res.get(g, {}).get("empirical_lag", {}).get("to_peak", {}).get("lag_h")
        flag = " ⚠ snapped to Calder" if g == "cragg_dauber_bridge" else ""
        lines.append(f"| {g}{flag} | {d['dem_area_km2']} | {f(d['nrfa_area_km2'], '{}')} | {f(d['area_ratio_dem_vs_nrfa'], '{:.2f}')} | "
                     f"{d['longest_flow_path_km']} | {d['relief_m']:.0f} | {d['kirpich_tc_h']:.1f} | {f(e, '{}')} |")
        if g != "cragg_dauber_bridge" and e is not None:
            tc.append(d["kirpich_tc_h"]); emp.append(e)
    rho = stats.spearmanr(tc, emp) if len(tc) >= 4 else None
    pr = stats.pearsonr(tc, emp) if len(tc) >= 4 else None
    mae = float(np.mean(np.abs(np.array(tc) - np.array(emp)))) if tc else None
    return "\n".join(lines), {"spearman": float(rho.statistic) if rho else None, "spearman_p": float(rho.pvalue) if rho else None,
                              "pearson": float(pr.statistic) if pr else None, "n": len(tc), "mae_h": mae}


def accuracy_tables(res) -> tuple[str, dict]:
    out, agg = [], {}
    for set_name, var in (("2024", "deployed"), ("2024", "oracle"), ("2024", "past")):
        lines = [f"**{set_name} · {var}**", "",
                 "| Gauge | " + " | ".join(f"{MN[m]} MAE / surge MAE (bias)" for m in M) + " |",
                 "|---|" + "---|" * len(M)]
        red_tfm, red_pers, surge_red = [], [], []
        for g, r in res.items():
            v = r["sets"].get(set_name, {}).get("variants", {}).get(var)
            if not v:
                continue
            cells = []
            for m in M:
                x = v[m]
                cells.append(f"{x['mae']:.3f} / {f(x['surge_mae'])} ({f(x['surge_bias'], '{:+.3f}')})")
            lines.append(f"| {g} | " + " | ".join(cells) + " |")
            red_tfm.append(1 - v["booster"]["mae"] / v["timesfm"]["mae"])
            red_pers.append(1 - v["booster"]["mae"] / v["persistence"]["mae"])
            if v["booster"]["surge_mae"] and v["timesfm"]["surge_mae"]:
                surge_red.append(1 - v["booster"]["surge_mae"] / v["timesfm"]["surge_mae"])
        agg[f"{set_name}_{var}"] = {"n": len(red_tfm),
                                    "mae_red_vs_timesfm_median": float(np.median(red_tfm)) if red_tfm else None,
                                    "mae_red_vs_persistence_median": float(np.median(red_pers)) if red_pers else None,
                                    "surge_mae_red_vs_timesfm_median": float(np.median(surge_red)) if surge_red else None}
        out.append("\n".join(lines))
    return "\n\n".join(out), agg


def storm_tables(res) -> tuple[str, dict]:
    lines, agg = [], {}
    for storm in ("ciara_dennis", "babet"):
        for var in ("past", "oracle"):
            lines += [f"**{storm} · {var}**  (peak error as % of the rise from origin to crest; timing error h; ✓ = within ±20% and ±3 h)", "",
                      "| Gauge | crest m | lead | " + " | ".join(MN[m] for m in M) + " |", "|---|---|---|" + "---|" * len(M)]
            cap = {m: {L: [] for L in ("6", "12")} for m in M}
            timing = {m: [] for m in M}
            magn = {m: [] for m in M}
            for g, r in res.items():
                v = r["sets"].get(storm, {}).get("variants", {}).get(var)
                if not v or not v.get("crest"):
                    continue
                c = v["crest"]
                for L in ("6", "12"):
                    lr = c["leads"].get(L)
                    if not lr or lr["rise_m"] <= 0.05:
                        continue
                    cells = []
                    for m in M:
                        x = lr.get(m)
                        if not x or x["peak_err_pct_of_rise"] is None:
                            cells.append("—"); continue
                        cells.append(f"{x['peak_err_pct_of_rise']:+.0%}, {x['timing_err_h']:+d} h{' ✓' if x['captured'] else ''}")
                        cap[m][L].append(x["captured"])
                        timing[m].append(abs(x["timing_err_h"]))
                        magn[m].append(x["peak_err_pct_of_rise"])
                    lines.append(f"| {g} | {c['crest_m']:.2f} | {L} h | " + " | ".join(cells) + " |")
            agg[f"{storm}_{var}"] = {m: {"capture_6h": float(np.mean(cap[m]["6"])) if cap[m]["6"] else None,
                                         "capture_12h": float(np.mean(cap[m]["12"])) if cap[m]["12"] else None,
                                         "n_6h": len(cap[m]["6"]), "n_12h": len(cap[m]["12"]),
                                         "mean_abs_timing_h": float(np.mean(timing[m])) if timing[m] else None,
                                         "median_peak_err_pct": float(np.median(magn[m])) if magn[m] else None}
                                     for m in M}
            lines.append("")
    return "\n".join(lines), agg


def warning_table(res) -> tuple[str, dict]:
    lines = ["| Test set · variant | events | " + " | ".join(f"{MN[m]}: hit / mean lead h / FAR" for m in M) + " |",
             "|---|---|" + "---|" * len(M)]
    agg = {}
    for set_name, var in (("2024", "deployed"), ("2024", "oracle"), ("2024", "past"),
                          ("ciara_dennis", "oracle"), ("ciara_dennis", "past"), ("babet", "oracle"), ("babet", "past")):
        leads = {m: [] for m in M}
        warns = {m: [0, 0] for m in M}
        ev = 0
        for g, r in res.items():
            v = r["sets"].get(set_name, {}).get("variants", {}).get(var)
            if not v:
                continue
            w = v["warning"]
            ev += w["events"]
            for m in M:
                x = w["models"][m]
                leads[m] += x["leads_h"]
                if x["warnings"]:
                    warns[m][0] += round(x["false_alarm_ratio"] * x["warnings"]); warns[m][1] += x["warnings"]
        if not ev:
            continue
        row = {}
        cells = []
        for m in M:
            L = np.array(leads[m])
            hit = float((L > 0).mean()) if len(L) else None
            far = warns[m][0] / warns[m][1] if warns[m][1] else None
            row[m] = {"hit_rate": hit, "mean_lead_h": float(L.mean()) if len(L) else None,
                      "mean_lead_h_given_hit": float(L[L > 0].mean()) if (L > 0).any() else None, "far": far}
            cells.append(f"{f(hit, '{:.0%}')} / {f(row[m]['mean_lead_h'], '{:.1f}')} / {f(far, '{:.2f}')}")
        agg[f"{set_name}_{var}"] = {"events": ev, **row}
        lines.append(f"| {set_name} · {var} | {ev} | " + " | ".join(cells) + " |")
    return "\n".join(lines), agg


if __name__ == "__main__":
    res = load()
    p1, p1a = phase1_table()
    dem, dema = dem_table(res)
    acc, acca = accuracy_tables(res)
    st, sta = storm_tables(res)
    wt, wta = warning_table(res)
    summary = {"phase1": p1a, "dem_lag": dema, "accuracy": acca, "storms": sta, "warnings": wta,
               "gauges_evaluated": sorted(res)}
    (ROOT / "results" / "floodpulse_summary.json").write_text(json.dumps(summary, indent=1))
    (ROOT / "results" / "floodpulse_tables.md").write_text(
        "## Phase 1\n\n" + p1 + "\n\n## DEM\n\n" + dem + "\n\n## Accuracy\n\n" + acc +
        "\n\n## Storms\n\n" + st + "\n\n## Warnings\n\n" + wt + "\n")
    print(json.dumps(summary, indent=1))

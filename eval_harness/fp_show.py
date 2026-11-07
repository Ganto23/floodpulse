"""Pretty-print one gauge's stress-test result."""
import json, sys
M = ("persistence", "timesfm", "booster_nophys", "booster")
def show(slug):
    r = json.load(open(f"results/floodpulse/{slug}.json"))
    if "error" in r or "skipped" in r:
        print(slug, r.get("error") or r.get("skipped")); return
    print(f"== {slug}  θ(P99)={r['p99_threshold']:.2f}  DEM lag={r['dem_lag_h']}  empirical={r['empirical_lag']['to_peak']['lag_h']}h")
    for s, v in r["sets"].items():
        for var, vr in v["variants"].items():
            print(f" [{s}/{var}] " + " | ".join(
                f"{m} MAE {vr[m]['mae']:.3f} surge {vr[m]['surge_mae']:.3f}({vr[m]['surge_bias']:+.3f})" if vr[m]['surge_mae'] is not None
                else f"{m} MAE {vr[m]['mae']:.3f}" for m in M))
            c = vr["crest"]
            if c:
                for L, lr in c["leads"].items():
                    print(f"     crest {c['crest_m']:.2f}m lead {L}h rise {lr['rise_m']:.2f}: " + " | ".join(
                        f"{m} {lr[m]['peak_err_pct_of_rise']:+.0%} {lr[m]['timing_err_h']:+d}h{'✓' if lr[m]['captured'] else ''}"
                        for m in M if m in lr and lr[m]['peak_err_pct_of_rise'] is not None))
            w = vr["warning"]
            if w["events"]:
                print(f"     warn θ events={w['events']}: " + " | ".join(
                    f"{m} hit {w['models'][m]['hit_rate']:.0%} lead {w['models'][m]['mean_lead_h']:.1f}h FAR {w['models'][m]['false_alarm_ratio'] if w['models'][m]['false_alarm_ratio'] is None else round(w['models'][m]['false_alarm_ratio'],2)}" for m in M))
for s in sys.argv[1:]:
    show(s)

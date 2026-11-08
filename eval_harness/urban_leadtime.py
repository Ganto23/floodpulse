"""Experiment: does FloodPulse give a usable 6 h warning on fast-responding catchments?

Reads existing per-gauge results (no refitting). For each gauge, 2024 test year:
  Tc (DEM Kirpich), area; for each rain variant (past-only / deployed real forecasts / oracle perfect rain):
  number of P99 up-crossings, how many were warned >=1 h and >=6 h ahead (sustained warning), FAR.
Fast = Tc < 3 h (the 'urban-like' regime the claim is about).
"""
import json
from pathlib import Path
R = Path(__file__).parent
C = json.load(open(R / "data/rivers/catchments.json"))
rows = []
for f in sorted((R / "results/floodpulse").glob("*.json")):
    d = json.load(open(f)); g = d["gauge"]; c = C.get(g, {})
    if "2024" not in d["sets"]: continue
    s = d["sets"]["2024"]["variants"]
    for var in ("past", "deployed", "oracle"):
        if var not in s or not s[var].get("warning"): continue
        w = s[var]["warning"]
        for m in ("timesfm", "booster"):
            mm = w["models"][m]; L = mm["leads_h"]
            rows.append(dict(gauge=g, tc=c.get("kirpich_tc_h"), area=c.get("dem_area_km2"), var=var, model=m,
                             events=w["events"], ge1=sum(x >= 1 for x in L), ge6=sum(x >= 6 for x in L),
                             leads=L, far=mm["false_alarm_ratio"]))
json.dump(rows, open(R / "results/urban/leadtime.json", "w"), indent=1)

def agg(sel):
    e = sum(r["events"] for r in sel); return e, sum(r["ge1"] for r in sel), sum(r["ge6"] for r in sel)

print(f"{'gauge':22} {'Tc h':>5} {'km2':>6}  events | booster ≥1h/≥6h: past  deployed  oracle | FAR deployed")
for g in sorted({r["gauge"] for r in rows}, key=lambda g: C.get(g, {}).get("kirpich_tc_h", 99)):
    b = {r["var"]: r for r in rows if r["gauge"] == g and r["model"] == "booster"}
    def cell(v): r = b.get(v); return f"{r['ge1']}/{r['ge6']}" if r else "-"
    r0 = next(iter(b.values()))
    print(f"{g:22} {r0['tc']:5.1f} {r0['area']:6.0f}  {r0['events']:6} |              {cell('past'):>5} {cell('deployed'):>9} {cell('oracle'):>7} | {b['deployed']['far'] if b['deployed']['far'] is not None else float('nan'):.2f}")
for label, cond in (("FAST (Tc<3h)", lambda r: r["tc"] < 3), ("SLOW (Tc>=3h)", lambda r: r["tc"] >= 3)):
    print(f"\n{label}")
    for var in ("past", "deployed", "oracle"):
        for m in ("timesfm", "booster"):
            e, a, b6 = agg([r for r in rows if cond(r) and r["var"] == var and r["model"] == m])
            print(f"  {var:9} {m:8} crossings {e:3}  warned ≥1h {a:3} ({a/e:4.0%})  warned ≥6h {b6:3} ({b6/e:4.0%})")

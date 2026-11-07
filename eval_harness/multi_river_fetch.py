"""
FloodPulse multi-river ingestion. Real data only, from public APIs.

Per gauge, 2019-09-01 → 2024-12-31 (covers Storm Ciara/Dennis Feb 2020 and Storm Babet Oct 2023):
  y            EA Hydrology 15-min river level → hourly mean (m)
  ea_rain      EA Hydrology tipping-bucket rain gauges within RAIN_RADIUS_KM (up to 3, hourly sum, mean)
  ERA5         Open-Meteo archive, mean of 5 points around the gauge: precipitation, soil moisture
               (0–7, 7–28 cm), temperature, snowfall
  fc_*         Open-Meteo Previous-Runs archived day-ahead NWP forecasts (exist from ~2024 only)

Outputs
  data/rivers/<slug>.csv           full 2019-2024 hourly frame
  data/flood_<slug>.csv            2023-2024 slice in the exact Phase-0 schema (check_correlation.py)
  data/rivers/stations.json        metadata + coverage
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from fetch_data import DATA, get_json, month_chunks

START, END = "2019-09-01", "2024-12-31"
EA = "https://environment.data.gov.uk/hydrology"
RAIN_RADIUS_KM = 15
OUT = DATA / "rivers"

STATIONS = {
    "calder_mytholmroyd": ("River Calder", "Mytholmroyd", "8a2ef48d-ddc5-4643-a1cf-2da54a045d8e_F1204-level-i-900-m-qualified", 53.73084, -1.983888),
    "cragg_dauber_bridge": ("Cragg Brook", "Mytholmroyd Dauber Bridge", "9129bb7b-b639-4dac-83c4-2c6d3265ac21-level-i-900-m-qualified", 53.722779, -1.989756),
    "aire_armley": ("River Aire", "Armley (Leeds)", "655a16a0-8498-4b83-a8f6-6816952b2262-level-i-900-m-qualified", 53.801967, -1.575189),
    "calder_whalley": ("River Calder (Lancs)", "Whalley Weir", "b17f0895-5a5d-442c-bbad-fcf3280aae2f-level-i-900-m-qualified", 53.820037, -2.412708),
    "eden_sheepmount": ("River Eden", "Sheepmount (Carlisle)", "078cbfd9-31ae-46f4-bbcc-0dbdaa191cd3-level-i-900-m-qualified", 54.905047, -2.951874),
    "greta_low_briery": ("River Greta", "Low Briery (Keswick)", "94de4171-c8ca-4e4c-9897-9fe4a6576582-level-i-900-m-qualified", 54.608017, -3.107571),
    "wharfe_otley": ("River Wharfe", "Otley", "49076770-98e9-47b2-89b0-aa90d60ecdc1-level-i-900-m-qualified", 53.90827, -1.694684),
    "ribble_samlesbury": ("River Ribble", "Samlesbury", "6e4d9ef9-131a-4712-895e-52a05dc290e9-level-i-900-m-qualified", 53.768364, -2.624704),
    "kent_victoria_bridge": ("River Kent", "Victoria Bridge (Kendal)", "ad86da06-7fdf-4368-9662-cda79343d742-level-i-900-m-qualified", 54.330846, -2.74283),
    "derwent_ouse_bridge": ("River Derwent (Cumbria)", "Ouse Bridge", "6152bfd2-a1e8-408c-abd4-076bee104444-level-i-900-m-qualified", 54.677982, -3.244624),
}
ERA5_VARS = ["precipitation", "soil_moisture_0_to_7cm", "soil_moisture_7_to_28cm", "temperature_2m", "snowfall"]
FC_VARS = ["precipitation", "temperature_2m"]


def hourly_index():
    return pd.date_range(START, pd.Timestamp(END) + pd.Timedelta(hours=23), freq="h", tz="UTC")


def ea_readings(measure: str, months: int = 3) -> pd.Series:
    rows = []
    for a, b in month_chunks(START, END, months=months):
        d = get_json(f"{EA}/id/measures/{measure}/readings",
                     {"mineq-date": a.date().isoformat(),
                      "max-date": (b + pd.Timedelta(days=1)).date().isoformat(), "_limit": 2000000})
        rows += [(it["dateTime"], it.get("value"), it.get("quality")) for it in d.get("items", [])]
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=["t", "v", "q"])
    df["t"] = pd.to_datetime(df["t"], utc=True)
    df = df[~df["q"].fillna("Good").isin(["Suspect", "Missing"])]
    return pd.to_numeric(df.drop_duplicates("t").set_index("t")["v"], errors="coerce").sort_index()


def rain_gauges(lat: float, lon: float) -> list[tuple[str, str, float]]:
    d = get_json(f"{EA}/id/stations", {"observedProperty": "rainfall", "lat": lat, "long": lon,
                                       "dist": RAIN_RADIUS_KM, "_limit": 50})
    out = []
    for s in d.get("items", []):
        m = next((m["@id"].split("/")[-1] for m in s.get("measures", [])
                  if "rainfall-t-900" in m["@id"]), None)
        if m and s.get("lat") is not None:
            dist = float(np.hypot((s["lat"] - lat) * 111, (s["long"] - lon) * 111 * np.cos(np.radians(lat))))
            out.append((s.get("label", "?"), m, dist))
    return sorted(out, key=lambda x: x[2])


def open_meteo(url: str, pts, variables, suffix="") -> pd.DataFrame:
    frames = []
    for a, b in month_chunks(START, END, months=12):
        p = get_json(url, {"latitude": ",".join(str(x[0]) for x in pts), "longitude": ",".join(str(x[1]) for x in pts),
                           "start_date": a.date().isoformat(), "end_date": b.date().isoformat(),
                           "hourly": ",".join(f"{v}{suffix}" for v in variables), "timezone": "UTC"})
        for blk in (p if isinstance(p, list) else [p]):
            f = pd.DataFrame(blk["hourly"])
            f["time"] = pd.to_datetime(f["time"], utc=True)
            frames.append(f.set_index("time"))
    return pd.concat(frames).groupby(level=0).mean()


def build(slug: str) -> dict:
    river, label, measure, lat, lon = STATIONS[slug]
    level = ea_readings(measure)
    if level.empty:
        raise RuntimeError(f"{slug}: no level readings")
    y = level.resample("h").mean()

    gauges, rain = rain_gauges(lat, lon), []
    used = []
    for name, m, dist in gauges:
        s = ea_readings(m, months=6)
        if len(s) and s.notna().mean() > 0.5:
            rain.append(s.resample("h").sum(min_count=1).rename(name))
            used.append({"gauge": name, "km": round(dist, 1)})
        if len(rain) == 3:
            break
    ea_rain = pd.concat(rain, axis=1).mean(axis=1) if rain else pd.Series(dtype=float)

    pts = [(lat, lon)] + [(lat + dy, lon + dx) for dy, dx in ((0.08, 0), (-0.08, 0), (0, 0.12), (0, -0.12))]
    wx = open_meteo("https://archive-api.open-meteo.com/v1/archive", pts, ERA5_VARS)
    fc = open_meteo("https://previous-runs-api.open-meteo.com/v1/forecast", pts, FC_VARS, "_previous_day1")
    fc.columns = [f"fc_{c.replace('_previous_day1', '')}" for c in fc.columns]

    df = pd.DataFrame({"y": y, "ea_rain": ea_rain}).join(wx, how="outer").join(fc, how="left")
    df = df.reindex(hourly_index())
    df.index.name = "time"
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / f"{slug}.csv")

    # Phase-0-compatible 2023-2024 slice (same features as the original FloodPulse test)
    p0 = df.loc["2023-01-01":"2024-12-31", ["y", "precipitation", "soil_moisture_0_to_7cm",
                                             "soil_moisture_7_to_28cm", "temperature_2m",
                                             "fc_precipitation", "fc_temperature_2m"]].copy()
    p0["precip_6h"] = p0["precipitation"].rolling(6, min_periods=1).sum()
    p0["precip_24h"] = p0["precipitation"].rolling(24, min_periods=1).sum()
    p0.to_csv(DATA / f"flood_{slug}.csv")

    return {"slug": slug, "river": river, "label": label, "measure": measure, "lat": lat, "lon": lon,
            "level_readings": int(level.notna().sum()), "y_coverage": round(float(df["y"].notna().mean()), 4),
            "ea_rain_gauges": used, "ea_rain_coverage": round(float(df["ea_rain"].notna().mean()), 4),
            "fc_coverage": round(float(df["fc_precipitation"].notna().mean()), 4),
            "level_p50_p99_max": [round(float(x), 3) for x in df["y"].quantile([0.5, 0.99, 1.0])]}


def _safe(slug):
    try:
        return build(slug)
    except Exception as exc:
        return {"slug": slug, "error": f"{type(exc).__name__}: {exc}"[:300]}


if __name__ == "__main__":
    slugs = sys.argv[1:] or list(STATIONS)
    meta = {}
    with ThreadPoolExecutor(max_workers=1) as pool:   # sequential: EA gateway throttles parallel bursts
        for slug, res in zip(slugs, pool.map(lambda s: _safe(s), slugs)):
            meta[slug] = res
            print(f"== {slug}: {res}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stations.json").write_text(json.dumps(meta, indent=1))


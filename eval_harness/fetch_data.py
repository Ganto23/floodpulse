"""
Real-data acquisition for the three candidate ideas. Every series comes from a public API.
Output: data/<idea>.csv, hourly UTC index, column `y` = target, other columns = exogenous X.

  flood   EA Hydrology API (River Calder @ Mytholmroyd, 15-min level) + Open-Meteo catchment
  grid    Elexon BMRS demand outturn (INDO, half-hourly)            + Open-Meteo 5-city mean
  air     LAQN API (Marylebone Road MY1, hourly NO2)               + Open-Meteo central London

Raw API responses are cached under data/raw_cache/ so reruns don't hit the APIs.
Run:  .venv/bin/python fetch_data.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

START, END = "2023-01-01", "2024-12-31"
ROOT = Path(__file__).parent
DATA, CACHE = ROOT / "data", ROOT / "data" / "raw_cache"
UA = {"User-Agent": "eval-harness/0.1 (hackathon research)"}
PACE_S = 0.4   # be polite to public APIs (EA gateway throttles bursts)


# --------------------------------------------------------------------------- #
def get_json(url: str, params: dict | None = None, retries: int = 6, timeout: int = 180):
    key = hashlib.sha256((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()[:24]
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    last = None
    for attempt in range(retries):
        try:
            time.sleep(PACE_S)
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            if r.status_code == 403 and "Application-Gateway" in r.text:
                raise requests.HTTPError("HTTP 403 gateway throttle")   # transient: back off and retry
            if 400 <= r.status_code < 500:   # client error: retrying won't help
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            payload = r.json()
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
            return payload
        except RuntimeError:
            raise
        except Exception as exc:  # retry with backoff
            last = exc
            wait = 3 * 2 ** attempt
            print(f"   ! {url.split('?')[0][-60:]} failed ({exc}); retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"giving up on {url}: {last}")


def month_chunks(start=START, end=END, months=1):
    edges = pd.date_range(start, pd.Timestamp(end) + pd.Timedelta(days=1), freq=f"{months}MS")
    edges = edges.append(pd.DatetimeIndex([pd.Timestamp(end) + pd.Timedelta(days=1)])).unique()
    return [(a, b - pd.Timedelta(days=1)) for a, b in zip(edges[:-1], edges[1:])]


def day_chunks(days: int, start=START, end=END):
    a, end = pd.Timestamp(start), pd.Timestamp(end)
    while a <= end:
        b = min(a + pd.Timedelta(days=days - 1), end)
        yield a, b
        a = b + pd.Timedelta(days=1)


def hourly_index():
    return pd.date_range(START, pd.Timestamp(END) + pd.Timedelta(hours=23), freq="h", tz="UTC")


# --------------------------------------------------------------------------- #
# Open-Meteo (ERA5 reanalysis archive)
# --------------------------------------------------------------------------- #
OM_URL = "https://archive-api.open-meteo.com/v1/archive"


def open_meteo(points: list[tuple[float, float]], variables: list[str]) -> pd.DataFrame:
    """Hourly mean of `variables` across `points`."""
    payload = get_json(OM_URL, {
        "latitude": ",".join(str(p[0]) for p in points),
        "longitude": ",".join(str(p[1]) for p in points),
        "start_date": START, "end_date": END, "hourly": ",".join(variables), "timezone": "UTC",
    })
    blocks = payload if isinstance(payload, list) else [payload]
    frames = []
    for b in blocks:
        f = pd.DataFrame(b["hourly"])
        f["time"] = pd.to_datetime(f["time"], utc=True)
        frames.append(f.set_index("time"))
    return pd.concat(frames).groupby(level=0).mean()


PREV_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"


def issued_forecasts(points: list[tuple[float, float]], variables: list[str]) -> pd.DataFrame:
    """
    Real archived NWP forecasts issued ~1 day before each hour (`<var>_previous_day1`),
    returned as columns fc_<var>. Used to test with forecasts that were actually available,
    instead of an oracle.
    """
    frames = []
    for a, b in month_chunks(months=6):
        payload = get_json(PREV_RUNS_URL, {
            "latitude": ",".join(str(p[0]) for p in points),
            "longitude": ",".join(str(p[1]) for p in points),
            "start_date": a.date().isoformat(), "end_date": b.date().isoformat(),
            "hourly": ",".join(f"{v}_previous_day1" for v in variables), "timezone": "UTC",
        })
        for blk in (payload if isinstance(payload, list) else [payload]):
            f = pd.DataFrame(blk["hourly"])
            f["time"] = pd.to_datetime(f["time"], utc=True)
            frames.append(f.set_index("time"))
    out = pd.concat(frames).groupby(level=0).mean()
    return out.rename(columns={f"{v}_previous_day1": f"fc_{v}" for v in variables})


# --------------------------------------------------------------------------- #
# Idea 1 — FloodPulse
# --------------------------------------------------------------------------- #
EA = "https://environment.data.gov.uk/hydrology"
CALDER_MEASURES = [  # primary + fallback station near Mytholmroyd
    "9129bb7b-b639-4dac-83c4-2c6d3265ac21-level-i-900-m-qualified",
    "8a2ef48d-ddc5-4643-a1cf-2da54a045d8e_F1204-level-i-900-m-qualified",
]
CALDER_CATCHMENT = [(53.714, -2.097), (53.742, -2.013), (53.723, -1.990)]  # Todmorden, Hebden Br., Mytholmroyd


def ea_level(measure: str) -> pd.Series:
    rows = []
    for a, b in month_chunks(months=3):
        d = get_json(f"{EA}/id/measures/{measure}/readings",
                     {"mineq-date": a.date().isoformat(), "max-date": (b + pd.Timedelta(days=1)).date().isoformat(),
                      "_limit": 200000})
        rows += [(it["dateTime"], it.get("value"), it.get("quality")) for it in d.get("items", [])]
    df = pd.DataFrame(rows, columns=["t", "v", "q"])
    if df.empty:
        raise RuntimeError(f"no readings for {measure}")
    df["t"] = pd.to_datetime(df["t"], utc=True)
    df = df[df["q"].fillna("Good").isin(["Good", "Estimated", "Unchecked"])]
    return pd.to_numeric(df.set_index("t")["v"], errors="coerce").sort_index()


def build_flood() -> tuple[pd.DataFrame, dict]:
    level, used = None, None
    for m in CALDER_MEASURES:
        try:
            level, used = ea_level(m), m
            break
        except Exception as exc:
            print(f"   ! measure {m} unusable: {exc}", file=sys.stderr)
    if level is None:
        raise RuntimeError("all Calder level measures failed")
    y = level.resample("h").mean()
    wx = open_meteo(CALDER_CATCHMENT, ["precipitation", "soil_moisture_0_to_7cm",
                                       "soil_moisture_7_to_28cm", "temperature_2m"])
    fc = issued_forecasts(CALDER_CATCHMENT, ["precipitation", "temperature_2m"])
    df = pd.DataFrame({"y": y}).join(wx, how="outer").join(fc, how="left").reindex(hourly_index())
    df["precip_6h"] = df["precipitation"].rolling(6, min_periods=1).sum()
    df["precip_24h"] = df["precipitation"].rolling(24, min_periods=1).sum()
    meta = {"source_y": f"EA Hydrology measure {used}", "units_y": "m (stage)",
            "raw_readings": int(level.notna().sum())}
    return df, meta


# --------------------------------------------------------------------------- #
# Idea 2 — GridPulse
# --------------------------------------------------------------------------- #
ELEXON = "https://data.elexon.co.uk/bmrs/api/v1/demand/outturn"
CITIES = [(51.507, -0.128), (52.486, -1.890), (53.481, -2.242), (53.800, -1.549), (55.864, -4.252)]


def build_grid() -> tuple[pd.DataFrame, dict]:
    rows = []
    for a, b in day_chunks(14):   # API caps ranges at 28 days inclusive
        d = get_json(ELEXON, {"settlementDateFrom": a.date().isoformat(),
                              "settlementDateTo": b.date().isoformat(), "format": "json"})
        rows += [(r["startTime"], r.get("initialDemandOutturn")) for r in d.get("data", [])]
    s = pd.DataFrame(rows, columns=["t", "v"]).drop_duplicates("t")
    s["t"] = pd.to_datetime(s["t"], utc=True)
    y = pd.to_numeric(s.set_index("t")["v"], errors="coerce").sort_index().resample("h").mean()
    wx = open_meteo(CITIES, ["temperature_2m", "shortwave_radiation", "wind_speed_10m"])
    fc = issued_forecasts(CITIES, ["temperature_2m", "shortwave_radiation", "wind_speed_10m"])
    df = pd.DataFrame({"y": y}).join(wx, how="outer").join(fc, how="left").reindex(hourly_index())
    df["heating_degree"] = (15.5 - df["temperature_2m"]).clip(lower=0)
    return df, {"source_y": "Elexon BMRS INDO (initial national demand outturn)", "units_y": "MW",
                "raw_readings": int(s["v"].notna().sum())}


# --------------------------------------------------------------------------- #
# Idea 3 — AirPulse
# --------------------------------------------------------------------------- #
LAQN = "https://api.erg.ic.ac.uk/AirQuality/Data/SiteSpecies/SiteCode={site}/SpeciesCode=NO2/StartDate={a}/EndDate={b}/Json"
AIR_SITES = ["MY1", "KC1", "BL0"]  # Marylebone Rd; fallbacks: N. Kensington, Bloomsbury
LONDON = [(51.522, -0.155)]


def build_air() -> tuple[pd.DataFrame, dict]:
    for site in AIR_SITES:
        rows = []
        for a, b in month_chunks(months=1):
            d = get_json(LAQN.format(site=site, a=a.date(), b=(b + pd.Timedelta(days=1)).date()))
            rows += [(r["@MeasurementDateGMT"], r["@Value"]) for r in d["RawAQData"].get("Data", [])]
        s = pd.DataFrame(rows, columns=["t", "v"]).drop_duplicates("t")
        s["t"] = pd.to_datetime(s["t"]).dt.tz_localize("UTC")   # LAQN reports GMT
        y = pd.to_numeric(s.set_index("t")["v"].replace("", np.nan), errors="coerce").sort_index()
        if y.notna().mean() > 0.6:
            break
        print(f"   ! {site} coverage {y.notna().mean():.0%}; trying next site", file=sys.stderr)
    wx = open_meteo(LONDON, ["wind_speed_10m", "boundary_layer_height", "temperature_2m", "precipitation"])
    fc = issued_forecasts(LONDON, ["wind_speed_10m", "boundary_layer_height", "temperature_2m", "precipitation"])
    df = pd.DataFrame({"y": y}).join(wx, how="outer").join(fc, how="left").reindex(hourly_index())
    return df, {"source_y": f"LAQN {site} NO2", "units_y": "µg/m³", "raw_readings": int(y.notna().sum())}


BUILDERS = {"flood": build_flood, "grid": build_grid, "air": build_air}

if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    summary = {}
    for name in sys.argv[1:] or BUILDERS:
        print(f"== {name}")
        t0 = time.time()
        try:
            df, meta = BUILDERS[name]()
        except Exception as exc:
            print(f"   FAILED: {exc}")
            summary[name] = {"ok": False, "error": str(exc)}
            continue
        df.index.name = "time"
        df.to_csv(DATA / f"{name}.csv")
        meta.update(ok=True, rows=len(df), y_coverage=round(float(df["y"].notna().mean()), 4),
                    features=[c for c in df.columns if c != "y" and not c.startswith("fc_")],
                    issued_forecasts={c: round(float(df[c].notna().mean()), 3) for c in df.columns if c.startswith("fc_")},
                    seconds=round(time.time() - t0, 1))
        summary[name] = meta
        print(f"   {meta}")
    (DATA / "fetch_summary.json").write_text(json.dumps(summary, indent=2, default=str))

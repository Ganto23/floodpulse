"""
GridPulse residual study: data acquisition.

Sources (all free, no key):
  INDO     Elexon /demand/outturn               initial national demand outturn (half-hourly)
  NDF      Elexon /datasets/NDF                 EVERY published National Demand Forecast (~48/day)
  weather  Open-Meteo ERA5 archive              temperature, cloud cover, solar irradiance, wind
  issued   Open-Meteo Previous-Runs archive     the weather forecast issued ~1 day earlier (fc_*)
  All weather is averaged over London, Birmingham, Manchester, Leeds and Glasgow.

Forecast definitions, rebuilt from the publication log (no look-ahead):
  ndf_da       DAY-AHEAD: latest NDF published by 10:00 UTC on D-1 (GB day-ahead auction gate)
  ndf_l{h}     latest NDF published ≥ h hours before the target hour (NESO's own intraday update)

Output: data/gridpulse.csv (hourly UTC). residual = indo − ndf_da   (>0: NESO under-forecast)
"""

from __future__ import annotations

import json
import sys
import time

import numpy as np
import pandas as pd

from fetch_data import CITIES, DATA, day_chunks, get_json, month_chunks

START, END = "2024-03-01", "2024-12-31"
ELEXON = "https://data.elexon.co.uk/bmrs/api/v1"
WX_VARS = ["temperature_2m", "cloud_cover", "shortwave_radiation", "wind_speed_10m"]
LEADS = (1, 3, 6)
DA_GATE_UTC_HOUR = 10


def fetch_indo() -> pd.Series:
    rows = []
    for a, b in day_chunks(14, START, END):
        d = get_json(f"{ELEXON}/demand/outturn", {"settlementDateFrom": a.date().isoformat(),
                                                   "settlementDateTo": b.date().isoformat(), "format": "json"})
        rows += [(r["startTime"], r["initialDemandOutturn"]) for r in d.get("data", [])]
    s = pd.DataFrame(rows, columns=["t", "v"]).drop_duplicates("t")
    s["t"] = pd.to_datetime(s["t"], utc=True)
    return s.set_index("t")["v"].astype(float).sort_index()


def fetch_ndf() -> pd.DataFrame:
    """Full publication log: (publishTime, startTime, demand)."""
    rows = []
    start = (pd.Timestamp(START) - pd.Timedelta(days=2)).date().isoformat()
    for a, _ in day_chunks(1, start, END):
        b = a + pd.Timedelta(days=1)
        d = get_json(f"{ELEXON}/datasets/NDF", {"publishDateTimeFrom": f"{a.date()}T00:00Z",
                                                 "publishDateTimeTo": f"{b.date()}T00:00Z", "format": "json"})
        rows += [(r["publishTime"], r["startTime"], r["demand"]) for r in d.get("data", [])
                 if r.get("boundary", "N") == "N"]
    df = pd.DataFrame(rows, columns=["pub", "t", "demand"])
    df["pub"] = pd.to_datetime(df["pub"], utc=True)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df.drop_duplicates(["pub", "t"]).sort_values(["t", "pub"])


def latest_before(ndf: pd.DataFrame, cutoff: pd.Series) -> pd.Series:
    """For each target half-hour t, the most recent forecast with pub ≤ cutoff[t]."""
    d = ndf.merge(cutoff.rename("cut"), left_on="t", right_index=True)
    d = d[d["pub"] <= d["cut"]]
    return d.sort_values("pub").groupby("t")["demand"].last()


def weather(url: str, variables: list[str], suffix: str = "") -> pd.DataFrame:
    frames = []
    for a, b in month_chunks(START, END, months=6):
        payload = get_json(url, {
            "latitude": ",".join(str(p[0]) for p in CITIES), "longitude": ",".join(str(p[1]) for p in CITIES),
            "start_date": a.date().isoformat(), "end_date": b.date().isoformat(),
            "hourly": ",".join(f"{v}{suffix}" for v in variables), "timezone": "UTC"})
        for blk in (payload if isinstance(payload, list) else [payload]):
            f = pd.DataFrame(blk["hourly"])
            f["time"] = pd.to_datetime(f["time"], utc=True)
            frames.append(f.set_index("time"))
    return pd.concat(frames).groupby(level=0).mean()


if __name__ == "__main__":
    t0 = time.time()
    print("== INDO outturn");  indo = fetch_indo();  print(f"   {len(indo):,} half-hours")
    print("== NDF publication log (1 request/day)"); ndf = fetch_ndf()
    print(f"   {len(ndf):,} rows, {ndf['pub'].nunique():,} publications")

    targets = pd.Series(indo.index, index=indo.index)
    gate = (targets.dt.floor("D") - pd.Timedelta(days=1) + pd.Timedelta(hours=DA_GATE_UTC_HOUR))
    half = pd.DataFrame({"indo": indo, "ndf_da": latest_before(ndf, gate)})
    for h in LEADS:
        # an hourly target starts at the full hour; the forecast must predate that start by ≥ h
        start_of_hour = targets.dt.floor("h")
        half[f"ndf_l{h}"] = latest_before(ndf, start_of_hour - pd.Timedelta(hours=h))
    da_lead = ((targets - gate).dt.total_seconds() / 3600)
    hourly = half.resample("h").mean()

    print("== weather (ERA5 actual + issued day-ahead NWP)")
    wx = weather("https://archive-api.open-meteo.com/v1/archive", WX_VARS)
    fc = weather("https://previous-runs-api.open-meteo.com/v1/forecast", WX_VARS, "_previous_day1")
    fc.columns = [f"fc_{c.replace('_previous_day1', '')}" for c in fc.columns]

    idx = pd.date_range(START, pd.Timestamp(END) + pd.Timedelta(hours=23), freq="h", tz="UTC")
    df = hourly.join(wx, how="left").join(fc, how="left").reindex(idx)
    df["residual"] = df["indo"] - df["ndf_da"]
    df.index.name = "time"
    df.to_csv(DATA / "gridpulse.csv")

    cov = {c: round(float(df[c].notna().mean()), 4) for c in df.columns}
    summary = {"hours": len(df), "coverage": cov, "ndf_publications": int(ndf["pub"].nunique()),
               "da_lead_hours": [round(float(da_lead.min()), 1), round(float(da_lead.max()), 1)],
               "seconds": round(time.time() - t0, 1)}
    (DATA / "gridpulse_fetch_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))

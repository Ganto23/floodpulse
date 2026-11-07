"""
Open-Meteo Historical Weather connector.

Pulls real ERA5 reanalysis (rain, temperature, wind) from
https://archive-api.open-meteo.com/v1/archive for the dataset's bbox. The bbox
is sampled at its centre plus four inner quadrant points and averaged, which is
plenty for city-scale H3 grids (ERA5 is ~25 km native).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from config import OPEN_METEO_ARCHIVE_URL
from loaders.http import cached_request

log = logging.getLogger(__name__)

HOURLY_VARS = ("temperature_2m", "precipitation", "wind_speed_10m")
DAILY_VARS = ("temperature_2m_mean", "precipitation_sum", "wind_speed_10m_max")
RENAME = {
    "temperature_2m": "temperature", "temperature_2m_mean": "temperature",
    "precipitation": "precipitation", "precipitation_sum": "precipitation",
    "wind_speed_10m": "wind_speed", "wind_speed_10m_max": "wind_speed",
}
ARCHIVE_START = date(1940, 1, 1)
ARCHIVE_LAG_DAYS = 5
MAX_HOURLY_DAYS = 366


@dataclass
class WeatherResult:
    frame: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["temperature", "precipitation", "wind_speed"]))
    granularity: str = "none"
    online: bool = False
    source: str = "none"
    rows: int = 0
    notes: list[str] = field(default_factory=list)


class OpenMeteoWeatherLoader:
    def __init__(self, bbox: tuple[float, float, float, float]) -> None:
        s, w, n, e = bbox
        cy, cx = (s + n) / 2, (w + e) / 2
        qy, qx = (n - s) / 4, (e - w) / 4
        pts = [(cy, cx), (cy + qy, cx + qx), (cy + qy, cx - qx), (cy - qy, cx + qx), (cy - qy, cx - qx)]
        # dedupe points that collapse (tiny bboxes)
        self.points = list(dict.fromkeys((round(a, 3), round(b, 3)) for a, b in pts))

    def load(self, start: pd.Timestamp, end: pd.Timestamp, granularity: str = "auto") -> WeatherResult:
        res = WeatherResult()
        s_date = max(start.date(), ARCHIVE_START)
        e_date = min(end.date(), date.today() - timedelta(days=ARCHIVE_LAG_DAYS))
        if s_date > e_date:
            res.notes.append(f"requested window {start.date()}..{end.date()} outside archive coverage")
            return res
        if granularity == "auto":
            granularity = "hourly" if (e_date - s_date).days <= MAX_HOURLY_DAYS else "daily"
        if e_date < end.date():
            res.notes.append(f"archive ends {e_date} (ERA5 lag); later bins carry no weather")

        variables = HOURLY_VARS if granularity == "hourly" else DAILY_VARS
        params = {
            "latitude": ",".join(str(p[0]) for p in self.points),
            "longitude": ",".join(str(p[1]) for p in self.points),
            "start_date": s_date.isoformat(), "end_date": e_date.isoformat(),
            granularity: ",".join(variables), "timezone": "UTC",
        }
        try:
            payload, cached = cached_request("openmeteo", "GET", OPEN_METEO_ARCHIVE_URL, params=params)
        except Exception as exc:
            log.warning("Open-Meteo unavailable: %s", exc)
            res.notes.append(f"Open-Meteo request failed: {exc}")
            return res

        blocks = payload if isinstance(payload, list) else [payload]
        frames = []
        for blk in blocks:
            data = blk.get(granularity)
            if not data:
                continue
            f = pd.DataFrame(data)
            f["time"] = pd.to_datetime(f["time"], utc=True)
            frames.append(f.set_index("time"))
        if not frames:
            res.notes.append(f"Open-Meteo returned no {granularity} block")
            return res

        frame = pd.concat(frames).groupby(level=0).mean().rename(columns=RENAME)
        res.frame = frame[["temperature", "precipitation", "wind_speed"]].sort_index()
        res.granularity, res.online, res.rows = granularity, True, len(res.frame)
        res.source = "open-meteo:cache" if cached else "open-meteo:live"
        return res

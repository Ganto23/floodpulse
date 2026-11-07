"""
Housing transactions loader (DATASET_MODE="housing").

Reads a real geocoded sales file from /data/raw/housing_transactions.csv
(e.g. Zillow/Redfin exports, NYC Rolling Sales joined to PLUTO, King County
house sales `kc_house_data.csv`). `value` is the sale price, so tensor
activity becomes price-weighted volume.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import RAW_DIR
from loaders.base import BaseDataLoader, LoaderError

LAT = ("latitude", "lat")
LON = ("longitude", "lon", "lng", "long")
TS = ("date", "sale_date", "date_of_transfer", "timestamp", "sold_date", "closing_date")
PRICE = ("price", "sale_price", "value", "amount", "sold_price")
NEW = ("new_build", "old_new", "is_new", "new_construction", "yr_built")


class HousingTransactionLoader(BaseDataLoader):
    name = "housing"

    def load_data(self) -> pd.DataFrame:
        path = RAW_DIR / "housing_transactions.csv"
        if not path.exists():
            raise LoaderError(f"DATASET_MODE=housing requires {path} (see data/raw/README.md)")
        raw = pd.read_csv(path, low_memory=False)
        lat_c, lon_c, ts_c, price_c = (self.find_column(raw, a) for a in (LAT, LON, TS, PRICE))
        if not all((lat_c, lon_c, ts_c)):
            raise LoaderError(f"housing file needs lat/lon/date columns; got {list(raw.columns)[:15]}")

        ts = self.parse_timestamps(raw[ts_c].astype(str).str.replace(r"T000000$", "", regex=True))
        value = pd.to_numeric(raw[price_c], errors="coerce") if price_c else pd.Series(1.0, index=raw.index)

        new_c = self.find_column(raw, NEW)
        if new_c and new_c.lower() == "yr_built":
            is_new = pd.to_numeric(raw[new_c], errors="coerce") >= (ts.dt.year - 1)
        elif new_c:
            is_new = raw[new_c].astype(str).str.upper().isin({"Y", "TRUE", "1", "NEW"})
        else:
            is_new = pd.Series(False, index=raw.index)

        self.report.source, self.report.path, self.report.online = "raw_csv", str(path), True
        return self.standardize(pd.DataFrame({
            "latitude": raw[lat_c], "longitude": raw[lon_c], "timestamp": ts,
            "value": value, "category": np.where(is_new.fillna(False), "new_build", "resale"),
        }))

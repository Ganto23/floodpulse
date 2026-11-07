"""
Pokémon GO telemetry loader (ACTIVE mode).

Reads real crowdsourced scanner dumps placed in /data/raw:

  1. pokemon_telemetry.csv   — flat rows (RocketMap / PokemonGo-Map style exports)
  2. pokemon_telemetry.json  — list of records, or {"pokestops": [...], "gyms": [...]}
  3. pokestops.geojson       — Point features (community PokéStop maps)

If none are present it degrades gracefully to the real OSM amenity stream for
the target bbox (PokéStops/Gyms are predominantly seeded from these POIs). It
never invents rows.

Column names are matched case-insensitively against generous alias lists so
most public dumps load unmodified.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from config import RAW_DIR, TARGET_BBOX
from loaders.base import BaseDataLoader, LoaderError
from loaders.osm_loader import OSMAmenityLoader

log = logging.getLogger(__name__)

LAT = ("latitude", "lat", "y")
LON = ("longitude", "lon", "lng", "long", "x")
TS = ("timestamp", "time", "datetime", "last_modified", "last_updated", "updated",
      "updated_at", "date", "seen_at", "observed_at", "last_scanned", "created_at")
LURE = ("lure_expiration", "lure_expires", "lured", "is_lured", "lure_active", "lure",
        "active_fort_modifier", "active_pokemon_id", "lure_id")
KIND = ("type", "kind", "fort_type", "entity", "category", "poi_type")
NAME = ("name", "amenity", "title", "description")
VALUE = ("value", "count", "weight", "activity")
GYM_HINT_COLS = ("team_id", "team", "gym_points", "slots_available", "guard_pokemon_id")

FALSY = {"", "0", "false", "f", "no", "n", "none", "nan", "null", "0.0"}


class PokemonTelemetryLoader(BaseDataLoader):
    name = "pokemon"

    def __init__(self, raw_dir: Path = RAW_DIR) -> None:
        super().__init__()
        self.raw_dir = raw_dir

    # ------------------------------------------------------------------ #
    def load_data(self) -> pd.DataFrame:
        csv_p = self.raw_dir / "pokemon_telemetry.csv"
        json_p = self.raw_dir / "pokemon_telemetry.json"
        geo_p = self.raw_dir / "pokestops.geojson"

        if csv_p.exists():
            df = self._parse_tabular(pd.read_csv(csv_p, low_memory=False))
            self._mark("raw_csv", csv_p)
        elif json_p.exists():
            df = self._parse_json(json_p)
            self._mark("raw_json", json_p)
        elif geo_p.exists():
            df = self._parse_geojson(geo_p)
            self._mark("raw_geojson", geo_p)
        else:
            return self._fallback_osm()
        return self.standardize(df)

    def _mark(self, source: str, path: Path) -> None:
        self.report.source, self.report.path, self.report.online = source, str(path), True

    def _fallback_osm(self) -> pd.DataFrame:
        self.report.notes.append(
            "no pokemon_telemetry.{csv,json} or pokestops.geojson in data/raw — "
            "falling back to real OSM POI stream (PokéStop seed layer)"
        )
        osm = OSMAmenityLoader(TARGET_BBOX)
        df = osm.load_data()
        # Map OSM POIs into Pokémon semantics: landmark-ish POIs ~ Gyms, rest ~ PokéStops.
        gym_like = df["category"].str.contains(
            r"tourism:attraction|historic|leisure:park|amenity:place_of_worship|tourism:museum", regex=True)
        df["category"] = np.where(gym_like, "gym", "pokestop")
        self.report.source = f"fallback_osm({osm.report.source})"
        self.report.online = True
        self.report.notes.extend(osm.report.notes)
        self.report.rows_raw, self.report.rows_valid = osm.report.rows_raw, osm.report.rows_valid
        return df

    # ------------------------------------------------------------------ #
    # Parsers
    # ------------------------------------------------------------------ #
    def _parse_tabular(self, raw: pd.DataFrame, default_kind: str | None = None) -> pd.DataFrame:
        lat_c, lon_c, ts_c = (self.find_column(raw, a) for a in (LAT, LON, TS))
        if not (lat_c and lon_c):
            raise LoaderError(f"pokemon dump has no lat/lon columns (got {list(raw.columns)[:12]})")
        if not ts_c:
            raise LoaderError("pokemon dump has no timestamp column "
                              f"(looked for {TS}); a real time axis is required")

        ts = self.parse_timestamps(raw[ts_c])
        lured = self._lure_flags(raw, ts)
        kind = self._kinds(raw, default_kind)
        val_c = self.find_column(raw, VALUE)
        value = pd.to_numeric(raw[val_c], errors="coerce").fillna(1.0) if val_c else 1.0

        category = np.where(lured, "lure", kind)
        self.report.notes.append(
            f"columns: lat={lat_c} lon={lon_c} ts={ts_c} lured={int(lured.sum())} rows flagged"
        )
        return pd.DataFrame({
            "latitude": raw[lat_c], "longitude": raw[lon_c], "timestamp": ts,
            "value": value, "category": category,
        })

    def _lure_flags(self, raw: pd.DataFrame, ts: pd.Series) -> pd.Series:
        lure_c = self.find_column(raw, LURE)
        if lure_c is None:
            return pd.Series(False, index=raw.index)
        col = raw[lure_c]
        if "expir" in lure_c.lower():
            exp = self.parse_timestamps(col)
            # lured if the lure was still active at observation time
            return (exp.notna() & ((exp >= ts) | ts.isna())).fillna(False)
        if pd.api.types.is_bool_dtype(col):
            return col.fillna(False)
        if pd.api.types.is_numeric_dtype(col):
            return col.fillna(0) != 0
        return ~col.astype(str).str.strip().str.lower().isin(FALSY)

    def _kinds(self, raw: pd.DataFrame, default_kind: str | None) -> pd.Series:
        kind_c = self.find_column(raw, KIND)
        if kind_c is not None:
            k = raw[kind_c].astype(str).str.lower()
            return pd.Series(np.where(k.str.contains("gym"), "gym", "pokestop"), index=raw.index)
        if default_kind:
            return pd.Series(default_kind, index=raw.index)
        if any(self.find_column(raw, (h,)) for h in GYM_HINT_COLS):
            hint = next(c for h in GYM_HINT_COLS if (c := self.find_column(raw, (h,))))
            return pd.Series(np.where(raw[hint].notna(), "gym", "pokestop"), index=raw.index)
        return pd.Series("pokestop", index=raw.index)

    def _parse_json(self, path: Path) -> pd.DataFrame:
        payload = json.loads(path.read_text())
        frames: list[pd.DataFrame] = []
        if isinstance(payload, list):
            frames.append(self._parse_tabular(pd.json_normalize(payload)))
        elif isinstance(payload, dict):
            for key, kind in (("pokestops", "pokestop"), ("gyms", "gym"),
                              ("forts", None), ("data", None), ("records", None)):
                if isinstance(payload.get(key), list) and payload[key]:
                    frames.append(self._parse_tabular(pd.json_normalize(payload[key]), kind))
        if not frames:
            raise LoaderError(f"{path.name}: expected a list or pokestops/gyms/forts arrays")
        return pd.concat(frames, ignore_index=True)

    def _parse_geojson(self, path: Path) -> pd.DataFrame:
        gj = json.loads(path.read_text())
        rows = []
        for f in gj.get("features", []):
            g = f.get("geometry") or {}
            if g.get("type") != "Point":
                continue
            props = dict(f.get("properties") or {})
            props["longitude"], props["latitude"] = g["coordinates"][:2]
            rows.append(props)
        if not rows:
            raise LoaderError(f"{path.name}: no Point features")
        return self._parse_tabular(pd.DataFrame(rows))

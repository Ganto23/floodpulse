"""
Abstract Data Adapter.

Every dataset — Pokémon GO telemetry, OSM edits, housing sales — is mapped to the
same frame layout (one row per StandardSpatialEvent):

    latitude: float | longitude: float | timestamp: datetime64[ns, UTC]
    value: float    | category: str

Downstream code (H3 indexer, tensor engine, forecaster, API) only ever sees this
layout, which is what makes the pipeline plug-and-play.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

STANDARD_COLUMNS: tuple[str, ...] = ("latitude", "longitude", "timestamp", "value", "category")


class StandardSpatialEvent(BaseModel):
    """Unified schema contract (used for validation + API docs)."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timestamp: datetime
    value: float
    category: str


@dataclass
class LoaderReport:
    """Provenance for /api/status — proves where the rows actually came from."""

    source: str = "none"
    path: str | None = None
    rows_raw: int = 0
    rows_valid: int = 0
    notes: list[str] = field(default_factory=list)
    online: bool = False


class LoaderError(RuntimeError):
    """Raised when no real data source could be found or parsed."""


class BaseDataLoader(ABC):
    """Base class for all dataset adapters."""

    name: str = "base"
    # Loaders may override the mode's highlighted category when their source
    # carries a different real signal (e.g. Kaggle spawns have no lure field).
    highlight_category: str | None = None
    highlight_label: str | None = None
    value_label: str | None = None
    event_noun: str | None = None

    def __init__(self) -> None:
        self.report = LoaderReport()

    @abstractmethod
    def load_data(self) -> pd.DataFrame:
        """Return a frame with exactly STANDARD_COLUMNS (see `standardize`)."""

    # ------------------------------------------------------------------ #
    # Shared helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def find_column(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
        lowered = {c.lower().strip(): c for c in df.columns}
        for alias in aliases:
            if alias in lowered:
                return lowered[alias]
        return None

    @staticmethod
    def parse_timestamps(series: pd.Series) -> pd.Series:
        """Parse ISO strings, epoch seconds or epoch milliseconds into UTC."""
        if pd.api.types.is_numeric_dtype(series):
            s = pd.to_numeric(series, errors="coerce")
            unit = "ms" if s.dropna().median() > 1e11 else "s"
            return pd.to_datetime(s, unit=unit, utc=True, errors="coerce")
        return pd.to_datetime(series, utc=True, errors="coerce", format="mixed")

    def standardize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Coerce types, drop invalid rows, enforce schema + sort order."""
        missing = [c for c in STANDARD_COLUMNS if c not in df.columns]
        if missing:
            raise LoaderError(f"{self.name}: loader output missing columns {missing}")

        out = df.loc[:, list(STANDARD_COLUMNS)].copy()
        self.report.rows_raw = len(out)
        out["latitude"] = pd.to_numeric(out["latitude"], errors="coerce")
        out["longitude"] = pd.to_numeric(out["longitude"], errors="coerce")
        out["value"] = pd.to_numeric(out["value"], errors="coerce").fillna(1.0)
        out["category"] = out["category"].fillna("unknown").astype(str)
        if not isinstance(out["timestamp"].dtype, pd.DatetimeTZDtype):
            out["timestamp"] = self.parse_timestamps(out["timestamp"])

        valid = (
            out["latitude"].between(-90, 90)
            & out["longitude"].between(-180, 180)
            & out["timestamp"].notna()
            & ~((out["latitude"] == 0) & (out["longitude"] == 0))
        )
        dropped = int((~valid).sum())
        if dropped:
            self.report.notes.append(f"dropped {dropped} rows with invalid coords/timestamps")
        out = out[valid].sort_values("timestamp").reset_index(drop=True)
        self.report.rows_valid = len(out)
        if out.empty:
            raise LoaderError(f"{self.name}: no valid rows after standardization")
        return out

    @staticmethod
    def first_existing(paths: list[Path]) -> Path | None:
        return next((p for p in paths if p.exists() and p.stat().st_size > 0), None)

    def describe(self) -> dict[str, Any]:
        r = self.report
        return {
            "loader": self.name,
            "source": r.source,
            "path": r.path,
            "rows_raw": r.rows_raw,
            "rows_valid": r.rows_valid,
            "online": r.online,
            "notes": r.notes,
        }

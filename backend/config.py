"""
UrbanPulse global configuration.

`DATASET_MODE` is the single switch that re-routes the whole pipeline:
    "pokemon"  -> Pokémon GO PokéStop / Gym / Lure telemetry (default)
    "osm"      -> raw OpenStreetMap amenity edit stream
    "housing"  -> real-estate transaction records (price-weighted)

Every mode emits the same StandardSpatialEvent schema, so the tensor engine,
forecaster, signal layer and UI stay identical. Only the loader and the UI
descriptors in MODE_PROFILES change.

Any value can be overridden with an `URBANPULSE_<NAME>` environment variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = Path(os.getenv("URBANPULSE_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"


def _env(name: str, default):
    raw = os.getenv(f"URBANPULSE_{name}")
    if raw is None:
        return default
    if isinstance(default, bool):
        return raw.lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    if isinstance(default, tuple):
        return tuple(float(x) for x in raw.split(","))
    return raw


# --------------------------------------------------------------------------- #
# THE switch
# --------------------------------------------------------------------------- #
DATASET_MODE: str = _env("DATASET_MODE", "pokemon")


# --------------------------------------------------------------------------- #
# Mode profiles: loader wiring + UI descriptors
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ModeProfile:
    key: str
    label: str                 # shown in the telemetry sidebar
    stream_name: str           # "[ONLINE] <stream_name>"
    value_label: str           # what `value` means on the map legend
    event_noun: str            # "PokéStop", "transaction", ...
    highlight_category: str    # category rendered as point markers (lures, ...)
    highlight_label: str
    preferred_freq: str        # short-horizon bin (pandas offset alias)
    short_horizon_minutes: int # nowcast window (30-90 min for live telemetry)
    raw_files: tuple[str, ...] = field(default_factory=tuple)


MODE_PROFILES: dict[str, ModeProfile] = {
    "pokemon": ModeProfile(
        key="pokemon",
        label="Pokémon GO",
        stream_name="Real Spatial Telemetry Stream (Active Mode: Pokémon GO)",
        value_label="PokéStop / Gym activity",
        event_noun="PokéStop event",
        highlight_category="lure",
        highlight_label="Active Lures",
        preferred_freq="15min",
        short_horizon_minutes=90,
        raw_files=("pokemon_telemetry.csv", "pokemon_telemetry.json",
                   "pokestops.geojson"),
    ),
    "osm": ModeProfile(
        key="osm",
        label="OpenStreetMap",
        stream_name="Real Spatial Telemetry Stream (Active Mode: OSM Amenity Edits)",
        value_label="Amenity edit activity",
        event_noun="amenity edit",
        highlight_category="transit",
        highlight_label="Transit Nodes",
        preferred_freq="1D",
        short_horizon_minutes=60 * 24 * 7,
        raw_files=("osm_amenities.geojson",),
    ),
    "housing": ModeProfile(
        key="housing",
        label="Housing",
        stream_name="Real Spatial Telemetry Stream (Active Mode: Housing Transactions)",
        value_label="Transaction volume (price-weighted)",
        event_noun="transaction",
        highlight_category="new_build",
        highlight_label="New-build Sales",
        preferred_freq="1W",
        short_horizon_minutes=60 * 24 * 28,
        raw_files=("housing_transactions.csv",),
    ),
}


def active_profile() -> ModeProfile:
    if DATASET_MODE not in MODE_PROFILES:
        raise ValueError(
            f"Unknown DATASET_MODE={DATASET_MODE!r}; "
            f"expected one of {sorted(MODE_PROFILES)}"
        )
    return MODE_PROFILES[DATASET_MODE]


# --------------------------------------------------------------------------- #
# Geography
# --------------------------------------------------------------------------- #
# Fallback target area when the raw dataset doesn't define one
# (south, west, north, east). Default: downtown San Francisco.
TARGET_BBOX: tuple[float, float, float, float] = _env(
    "TARGET_BBOX", (37.770, -122.430, 37.810, -122.390)
)
# Overpass refuses huge boxes; cap the area we will ever query (degrees^2).
MAX_OVERPASS_AREA: float = _env("MAX_OVERPASS_AREA", 0.01)

H3_RESOLUTION: int = _env("H3_RESOLUTION", 9)   # 8 ≈ 0.74 km², 9 ≈ 0.11 km²
CATCHMENT_RINGS: int = _env("CATCHMENT_RINGS", 3)  # k-rings ≈ 5/10/15 min walk @ res 9

# --------------------------------------------------------------------------- #
# External APIs
# --------------------------------------------------------------------------- #
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OVERPASS_URL: str = _env("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
HTTP_TIMEOUT_S: float = _env("HTTP_TIMEOUT_S", 90.0)
USER_AGENT = "UrbanPulse/0.1 (hackathon research prototype)"

# --------------------------------------------------------------------------- #
# Tensor engine
# --------------------------------------------------------------------------- #
MAX_TIME_STEPS: int = _env("MAX_TIME_STEPS", 672)     # most-recent bins kept
MAX_CELLS: int = _env("MAX_CELLS", 800)               # busiest H3 cells kept
FOCUS_RESOLUTION: int = _env("FOCUS_RESOLUTION", 5)   # densest res-5 region = study area
MIN_BIN_DENSITY: float = _env("MIN_BIN_DENSITY", 0.10)  # coarsen freq below this
TUCKER_RANK_SPATIAL: int = _env("TUCKER_RANK_SPATIAL", 12)
TUCKER_RANK_TEMPORAL: int = _env("TUCKER_RANK_TEMPORAL", 8)
TUCKER_RANK_FEATURE: int = _env("TUCKER_RANK_FEATURE", 3)
LONG_RANGE_FREQ = "MS"                       # month-start bins for multi-year view
LONG_RANGE_END: str = _env("LONG_RANGE_END", "2030-12-01")
LONG_RANGE_MIN_PERIODS: int = _env("LONG_RANGE_MIN_PERIODS", 12)

# --------------------------------------------------------------------------- #
# Forecasting
# --------------------------------------------------------------------------- #
# "auto" tries timesfm -> chronos -> statistical fallback (damped Holt).
FORECAST_BACKEND: str = _env("FORECAST_BACKEND", "auto")
TIMESFM_REPO: str = _env("TIMESFM_REPO", "google/timesfm-2.5-200m-pytorch")
TIMESFM_V1_REPO: str = _env("TIMESFM_V1_REPO", "google/timesfm-1.0-200m-pytorch")
CHRONOS_REPO: str = _env("CHRONOS_REPO", "amazon/chronos-bolt-small")

# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #
SURGE_Z: float = _env("SURGE_Z", 2.0)        # momentum z-score -> velocity surge
ANOMALY_Z: float = _env("ANOMALY_Z", 3.0)    # residual z-score -> anomaly
DISPATCH_Z: float = _env("DISPATCH_Z", 2.5)  # forecast z-score -> dispatch trigger

CORS_ORIGINS: str = _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

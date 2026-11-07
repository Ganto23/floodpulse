"""Pydantic API contracts (mirrored in frontend/src/lib/types.ts)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class SourceStatus(BaseModel):
    key: str
    label: str
    state: Literal["ONLINE", "DEGRADED", "OFFLINE", "LOADING"]
    detail: str
    metrics: dict[str, Any] = {}


class ModeDescriptor(BaseModel):
    key: str
    label: str
    value_label: str
    event_noun: str
    highlight_label: str


class StatusResponse(BaseModel):
    pipeline: Literal["idle", "loading", "ready", "error"]
    stage: str
    error: str | None
    mode: ModeDescriptor
    sources: list[SourceStatus]
    tensor: dict[str, Any]
    notes: list[str]
    elapsed_s: float | None


class TimelineFrame(BaseModel):
    timestamp: str
    kind: Literal["historical", "forecast"]
    regime: Literal["nowcast", "longrange"]


class TimelineResponse(BaseModel):
    start: str
    end: str
    history_end: str
    forecast_end: str
    frames: list[TimelineFrame]
    bbox: tuple[float, float, float, float]
    center: tuple[float, float]


class CellProperties(BaseModel):
    h3: str
    realized: float | None
    denoised: float | None
    forecast: float | None
    forecast_lo: float | None
    forecast_hi: float | None
    momentum: float
    signal: str | None


class CellFeature(BaseModel):
    type: Literal["Feature"]
    geometry: dict[str, Any]
    properties: CellProperties


class Highlight(BaseModel):
    latitude: float
    longitude: float
    category: str
    timestamp: str


class CatchmentRing(BaseModel):
    k: int
    walk_minutes: int
    coordinates: list[Any]


class Catchment(BaseModel):
    h3: str
    type: str
    rings: list[CatchmentRing]


class Signal(BaseModel):
    id: str
    type: Literal["VELOCITY_SURGE", "MOMENTUM_DECAY", "ANOMALY", "DISPATCH"]
    severity: Literal["critical", "high", "medium"]
    h3: str
    latitude: float
    longitude: float
    z: float
    message: str
    action: str


class FrameMeta(BaseModel):
    timestamp: str
    kind: Literal["historical", "forecast"]
    regime: str
    freq: str
    horizon_label: str
    value_label: str
    momentum_unit: str
    max_surface: float
    weather: dict[str, float | None] | None


class SpatialFrameResponse(BaseModel):
    type: Literal["FeatureCollection"]
    features: list[CellFeature]
    meta: FrameMeta
    highlights: list[Highlight]
    vectors: list[dict[str, Any]]
    catchments: list[Catchment]
    signals: list[Signal]


class InfrastructureResponse(BaseModel):
    transit: list[dict[str, Any]]
    paths: list[list[list[float]]]
    source: str


class BacktestResponse(BaseModel):
    status: Literal["pending", "running", "ready", "error"]
    error: str | None = None
    result: dict[str, Any] | None = None

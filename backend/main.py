"""
UrbanPulse FastAPI service.

    uvicorn main:app --reload --port 8000      (from /backend)
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import config
from engine.pipeline import UrbanPulsePipeline
from schemas import (InfrastructureResponse, ModeDescriptor, SourceStatus, SpatialFrameResponse,
                     StatusResponse, TimelineFrame, TimelineResponse)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
pipeline = UrbanPulsePipeline()


@asynccontextmanager
async def lifespan(_: FastAPI):
    pipeline.start_background()   # API is up immediately; /api/status reports progress
    yield


app = FastAPI(title="UrbanPulse", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS.split(","),
                   allow_methods=["*"], allow_headers=["*"])


def _require_ready() -> None:
    st = pipeline.state
    if st.status != "ready":
        raise HTTPException(503, detail={"pipeline": st.status, "stage": st.stage, "error": st.error})


@app.get("/api/status", response_model=StatusResponse)
def status() -> StatusResponse:
    st, prof = pipeline.state, pipeline.profile
    loading = st.status in ("idle", "loading")

    def state(ok: bool, degraded: bool = False):
        if ok:
            return "DEGRADED" if degraded else "ONLINE"
        return "LOADING" if loading else "OFFLINE"

    ld = st.loader or {}
    rows = len(st.events) if st.events is not None else 0
    fallback = str(ld.get("source", "")).startswith("fallback")
    sources = [SourceStatus(
        key="telemetry", label=prof.stream_name,
        state=state(rows > 0, fallback),
        detail=f"{ld.get('source', '…')} · {rows:,} events · {len(st.cells)} H3 cells",
        metrics={"rows_ingested": rows, "rows_raw": ld.get("rows_raw", 0), "cells": len(st.cells),
                 "source": ld.get("source"), "notes": ld.get("notes", [])},
    )]

    wx = [r.weather for r in st.regimes.values()]
    wx_rows = sum(w.rows for w in wx)
    sources.append(SourceStatus(
        key="weather", label="Open-Meteo Historical Weather API",
        state=state(any(w.online for w in wx)),
        detail=(" · ".join(f"{w.granularity}:{w.rows:,} rows ({w.source})" for w in wx) or "pending"),
        metrics={"rows": wx_rows, "notes": [n for w in wx for n in w.notes]},
    ))

    infra = st.infra
    sources.append(SourceStatus(
        key="osm", label="OpenStreetMap Transit Network",
        state=state(bool(infra and infra.online)),
        detail=(f"{len(infra.transit)} transit nodes · {len(infra.paths)} ped. ways · "
                f"{len(infra.buildings)} buildings ({infra.source})") if infra else "pending",
        metrics={"node_count": infra.node_count if infra else 0,
                 "notes": infra.notes if infra else []},
    ))

    fc_ready = bool(st.regimes)
    fdesc = pipeline.forecaster.describe() if fc_ready else {}
    sources.append(SourceStatus(
        key="forecast", label="TimesFM Zero-Shot Forecasting Engine",
        state=state(fc_ready, fc_ready and not fdesc.get("zero_shot_transformer")),
        detail=fdesc.get("backend", "pending"),
        metrics=fdesc,
    ))

    tensor = {
        name: {
            "shape": list(r.tensor.X.shape), "freq": r.tensor.freq, "ranks": list(r.tensor.ranks),
            "activity_rel_error": round(r.tensor.rel_error, 4),
            "temporal_explained": r.tensor.explained_variance(),
            "horizon_steps": len(r.horizon_times),
            "history": [r.tensor.times[0].isoformat(), r.tensor.times[-1].isoformat()],
            "notes": r.tensor.notes,
        } for name, r in st.regimes.items()
    }
    elapsed = ((st.finished_at or time.time()) - st.started_at) if st.started_at else None
    return StatusResponse(
        pipeline=st.status, stage=st.stage, error=st.error,
        mode=ModeDescriptor(key=prof.key, label=prof.label, value_label=prof.value_label,
                            event_noun=prof.event_noun, highlight_label=prof.highlight_label),
        sources=sources, tensor=tensor, notes=st.notes,
        elapsed_s=round(elapsed, 1) if elapsed else None,
    )


@app.get("/api/timeline", response_model=TimelineResponse)
def timeline() -> TimelineResponse:
    _require_ready()
    st = pipeline.state
    frames = st.frames
    hist = [f for f in frames if f.kind == "historical"]
    s, w, n, e = st.bbox
    return TimelineResponse(
        start=frames[0].ts.isoformat(), end=frames[-1].ts.isoformat(),
        history_end=hist[-1].ts.isoformat(), forecast_end=frames[-1].ts.isoformat(),
        frames=[TimelineFrame(timestamp=f.ts.isoformat(), kind=f.kind, regime=f.regime.name) for f in frames],
        bbox=st.bbox, center=((s + n) / 2, (w + e) / 2),
    )


@app.get("/api/spatial-frame", response_model=SpatialFrameResponse)
def spatial_frame(timestamp: datetime | None = Query(None, description="ISO-8601; defaults to latest realized bin")):
    _require_ready()
    return pipeline.frame_payload(timestamp)


@app.get("/api/infrastructure", response_model=InfrastructureResponse)
def infrastructure(max_paths: int = 4000) -> InfrastructureResponse:
    _require_ready()
    infra = pipeline.state.infra
    return InfrastructureResponse(
        transit=infra.transit.head(3000).to_dict("records"),
        paths=infra.paths[:max_paths], source=infra.source,
    )


@app.post("/api/refresh")
def refresh() -> dict:
    pipeline.start_background()
    return {"ok": True}

"""
FastAPI entrypoint.

Exposes:
  GET  /health          — status and number of records in the database
  POST /ingest          — ingest a JSON body (list of records)
  POST /ingest/file     — ingest a multipart JSON file
  POST /analyze         — run the pipeline over a rolling window or explicit range

The pipeline and repository are initialised once via the lifespan handler.
"""
from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field

from config import load_config
from domain.ingestor import IngestResult, ingest_file, ingest_records, parse_file
from domain.schemas import AnalyzeParams, Report
from infrastructure.repository import MetricRepository
from infrastructure.tracing import build_run_config
from pipeline.graph import build_pipeline


# ---------------------------------------------------------------------------
# Lifespan — single initialisation at startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    app.state.repo     = MetricRepository(config.db)
    app.state.pipeline = build_pipeline(config)
    yield


app = FastAPI(title="Monitoring AI", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class IngestBody(BaseModel):
    records: list[dict] = Field(..., min_length=1)


class IngestResponse(BaseModel):
    saved:    int
    errors:   int
    messages: list[str]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health(request: Request) -> dict:
    return {"status": "ok", "records_in_db": request.app.state.repo.count()}


@app.post("/ingest", response_model=IngestResponse)
def ingest(body: IngestBody, request: Request) -> IngestResponse:
    result: IngestResult = ingest_records(body.records, request.app.state.repo)
    if result.saved == 0 and result.errors > 0:
        raise HTTPException(status_code=422, detail=result.messages)
    return IngestResponse(saved=result.saved, errors=result.errors, messages=result.messages)


@app.post("/ingest/file", response_model=IngestResponse)
async def ingest_file_endpoint(
    request: Request,
    file: UploadFile = File(...),
) -> IngestResponse:
    content = await file.read()

    # Write to a temporary file to reuse ingest_file()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = ingest_file(tmp_path, request.app.state.repo)
    finally:
        os.unlink(tmp_path)

    if result.saved == 0 and result.errors > 0:
        raise HTTPException(status_code=422, detail=result.messages)
    return IngestResponse(saved=result.saved, errors=result.errors, messages=result.messages)


@app.post("/analyze/file", response_model=Report)
async def analyze_file_endpoint(
    request: Request,
    file: UploadFile = File(...),
) -> Report:
    """Analyse records from an uploaded JSON file without persisting them."""
    content = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        records, errors = parse_file(tmp_path)
    finally:
        os.unlink(tmp_path)

    if not records:
        raise HTTPException(status_code=422, detail=errors or ["No valid records in file."])

    start = min(r.timestamp for r in records)
    end   = max(r.timestamp for r in records)

    state = request.app.state.pipeline.invoke(
        {"records": records},
        build_run_config(len(records), start=start, end=end),
    )
    return state["report"]


@app.post("/analyze", response_model=Report)
def analyze(params: AnalyzeParams, request: Request) -> Report:
    repo     = request.app.state.repo
    pipeline = request.app.state.pipeline

    # Resolve the time range from whichever mode was requested
    if params.start and params.end:
        start, end     = params.start, params.end
        window_minutes = None
    else:
        end            = datetime.now(tz=timezone.utc)
        start          = end - timedelta(minutes=params.window_minutes)
        window_minutes = params.window_minutes

    records = repo.fetch_range(start, end)
    if not records:
        raise HTTPException(status_code=404, detail="No records found in the requested time range.")

    state = pipeline.invoke(
        {"records": records},
        build_run_config(len(records), start=start, end=end, window_minutes=window_minutes),
    )
    return state["report"]

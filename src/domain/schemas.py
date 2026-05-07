"""
Pydantic contracts — single coupling point between modules.

This file knows nothing about LangGraph, SQLite, FastAPI, or LangChain.
Any data crossing a module boundary is one of these models.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ServiceStatus(str, Enum):
    online   = "online"
    degraded = "degraded"
    offline  = "offline"


class Severity(str, Enum):
    critical = "critical"
    warning  = "warning"
    info     = "info"


class AnomalyStatus(str, Enum):
    active    = "active"     # still present at window_end
    recovered = "recovered"  # appeared then self-resolved within the window
    recurring = "recurring"  # appeared, resolved, then appeared again


class Priority(str, Enum):
    high   = "high"
    medium = "medium"
    low    = "low"


# ---------------------------------------------------------------------------
# Input: metric snapshot
# ---------------------------------------------------------------------------

class ServiceStatuses(BaseModel):
    database:    ServiceStatus
    api_gateway: ServiceStatus
    cache:       ServiceStatus


class MetricRecord(BaseModel):
    """System metric snapshot at a given point in time."""

    timestamp:               datetime
    cpu_usage:               float = Field(..., ge=0, le=100)
    memory_usage:            float = Field(..., ge=0, le=100)
    latency_ms:              float = Field(..., ge=0)
    disk_usage:              float = Field(..., ge=0, le=100)
    network_in_kbps:         float = Field(..., ge=0)
    network_out_kbps:        float = Field(..., ge=0)
    io_wait:                 float = Field(..., ge=0, le=100)
    thread_count:            int   = Field(..., ge=0)
    active_connections:      int   = Field(..., ge=0)
    error_rate:              float = Field(..., ge=0, le=1)
    uptime_seconds:          int   = Field(..., ge=0)
    temperature_celsius:     float = Field(..., ge=0)
    power_consumption_watts: float = Field(..., ge=0)
    service_status:          ServiceStatuses

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: object) -> datetime:
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Pipeline input parameters
# ---------------------------------------------------------------------------

class AnalyzeParams(BaseModel):
    """Parameters received by POST /analyze or the CLI analyze command.

    Two mutually exclusive modes:
      - Window mode (default): window_minutes minutes back from now.
      - Range mode: explicit start and end datetimes.

    If start/end are provided, window_minutes is ignored.
    """
    window_minutes: int             = Field(default=60, ge=30)
    start:          datetime | None = None
    end:            datetime | None = None

    @model_validator(mode="after")
    def validate_query_mode(self) -> "AnalyzeParams":
        has_start = self.start is not None
        has_end   = self.end   is not None
        if has_start ^ has_end:
            raise ValueError("'start' and 'end' must be provided together.")
        if has_start and has_end and self.start >= self.end:
            raise ValueError("'start' must be strictly before 'end'.")
        return self


# ---------------------------------------------------------------------------
# Node 1 output: analysis result
# ---------------------------------------------------------------------------

class Anomaly(BaseModel):
    metric:      str
    value:       float | str
    threshold:   float | str
    severity:    Severity
    description: str
    started_at:  datetime
    resolved_at: datetime | None = None
    status:      AnomalyStatus


class AnalysisResult(BaseModel):
    """Contract between the analysis node and the recommendation node."""
    window_start:   datetime
    window_end:     datetime
    record_count:   int
    anomalies:      list[Anomaly]
    summary:        str
    overall_health: Severity


# ---------------------------------------------------------------------------
# Node 2 output: final report
# ---------------------------------------------------------------------------

class Action(BaseModel):
    priority:    Priority
    category:    str
    title:       str
    description: str
    impact:      str


class Report(BaseModel):
    """Final report returned by the API and the CLI."""
    generated_at:      datetime
    window_start:      datetime
    window_end:        datetime
    overall_health:    Severity
    anomalies:         list[Anomaly]
    actions:           list[Action]
    executive_summary: str

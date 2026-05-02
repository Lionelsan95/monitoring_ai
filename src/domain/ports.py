"""
Domain interfaces (ports).

The domain depends on no concrete implementation.
Adapters (LangChain, SQLite, …) implement these protocols in infrastructure/.

Ports are expressed in domain terms — no mention of LLM, prompts, or JSON.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.schemas import (
        Action,
        AnalysisResult,
        Anomaly,
        MetricRecord,
    )


class AnomalyDetectorPort(Protocol):
    """Detects anomalies from a set of metric records.

    The adapter owns the model, the prompt, and the output parsing.
    The domain only sees domain objects in and domain objects out.
    """

    def detect(self, records: list["MetricRecord"]) -> tuple[str, list["Anomaly"]]:
        """Return (summary, anomalies) for the given records."""
        ...


class ActionPlannerPort(Protocol):
    """Generates a prioritised action plan from an analysis result.

    Same contract: the adapter owns all LLM details.
    """

    def plan(self, analysis: "AnalysisResult") -> tuple[str, list["Action"]]:
        """Return (executive_summary, actions) for the given analysis."""
        ...


class RepositoryPort(Protocol):
    """Minimal interface for MetricRecord persistence."""

    def save(self, record: "MetricRecord") -> None:
        ...

    def save_batch(self, records: list["MetricRecord"]) -> int:
        ...

    def fetch_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list["MetricRecord"]:
        """Return all records whose timestamp falls within [start, end]."""
        ...

    def count(self) -> int:
        ...

"""
Domain — metric ingestion.

Validates and persists raw metric snapshots (JSON dicts) to the database.
Uses RepositoryPort: no concrete dependency on SQLite.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from domain.ports import RepositoryPort
from domain.schemas import MetricRecord


@dataclass
class IngestResult:
    """Result of an ingestion operation."""
    saved:    int            = 0
    errors:   int            = 0
    messages: list[str]      = field(default_factory=list)


def ingest_records(raw: list[dict], repo: RepositoryPort) -> IngestResult:
    """
    Validate a list of raw dicts and persist the valid records.
    Invalid records are counted without interrupting the ingestion.
    """
    result = IngestResult()
    valid: list[MetricRecord] = []

    for i, item in enumerate(raw):
        try:
            valid.append(MetricRecord.model_validate(item))
        except ValidationError as e:
            result.errors += 1
            result.messages.append(f"Record {i}: {e.error_count()} validation error(s)")

    if valid:
        result.saved = repo.save_batch(valid)

    return result


def ingest_file(path: Path, repo: RepositoryPort) -> IngestResult:
    """
    Load a JSON file (single object or array of records) and delegate to ingest_records.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        result = IngestResult()
        result.errors = 1
        result.messages.append(f"Invalid JSON file: {e}")
        return result

    if isinstance(raw, dict):
        raw = [raw]

    return ingest_records(raw, repo)

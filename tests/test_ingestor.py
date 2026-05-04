"""Tests for the domain — ingestion."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from domain.ingestor import IngestResult, ingest_file, ingest_records, parse_file
from domain.schemas import MetricRecord, ServiceStatuses, ServiceStatus


# ---------------------------------------------------------------------------
# Mock repository — implements RepositoryPort without SQLite
# ---------------------------------------------------------------------------

class _MockRepo:
    def __init__(self) -> None:
        self.records: list[MetricRecord] = []

    def save(self, record: MetricRecord) -> None:
        self.records.append(record)

    def save_batch(self, records: list[MetricRecord]) -> int:
        self.records.extend(records)
        return len(records)

    def fetch_window(self, window_minutes: int, reference=None):
        return self.records

    def count(self) -> int:
        return len(self.records)


# ---------------------------------------------------------------------------
# ingest_records
# ---------------------------------------------------------------------------

def test_ingest_records_valid(sample_record: MetricRecord) -> None:
    repo   = _MockRepo()
    raw    = [sample_record.model_dump(mode="json")]
    result = ingest_records(raw, repo)

    assert result.saved  == 1
    assert result.errors == 0
    assert repo.count()  == 1


def test_ingest_records_partial_invalid(sample_record: MetricRecord) -> None:
    repo = _MockRepo()
    raw  = [
        sample_record.model_dump(mode="json"),  # valid
        {"this": "is not a metric record"},      # invalid
    ]
    result = ingest_records(raw, repo)

    assert result.saved  == 1
    assert result.errors == 1
    assert len(result.messages) == 1


def test_ingest_records_all_invalid() -> None:
    repo   = _MockRepo()
    result = ingest_records([{"bad": "data"}, {"also": "bad"}], repo)

    assert result.saved  == 0
    assert result.errors == 2
    assert repo.count()  == 0


# ---------------------------------------------------------------------------
# ingest_file
# ---------------------------------------------------------------------------

def test_ingest_file_array(sample_record: MetricRecord, tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text(json.dumps([sample_record.model_dump(mode="json")], default=str))
    repo   = _MockRepo()
    result = ingest_file(path, repo)

    assert result.saved == 1


def test_ingest_file_single_object(sample_record: MetricRecord, tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(sample_record.model_dump(mode="json"), default=str))
    repo   = _MockRepo()
    result = ingest_file(path, repo)

    assert result.saved == 1


def test_ingest_file_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not valid json {{{")
    repo   = _MockRepo()
    result = ingest_file(path, repo)

    assert result.saved  == 0
    assert result.errors == 1
    assert "Invalid JSON" in result.messages[0]


# ---------------------------------------------------------------------------
# parse_file
# ---------------------------------------------------------------------------

def test_parse_file_array(sample_record: MetricRecord, tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text(json.dumps([sample_record.model_dump(mode="json")], default=str))
    records, errors = parse_file(path)

    assert len(records) == 1
    assert errors       == []


def test_parse_file_single_object(sample_record: MetricRecord, tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(sample_record.model_dump(mode="json"), default=str))
    records, errors = parse_file(path)

    assert len(records) == 1
    assert errors       == []


def test_parse_file_partial_invalid(sample_record: MetricRecord, tmp_path: Path) -> None:
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps([
        sample_record.model_dump(mode="json"),
        {"bad": "data"},
    ], default=str))
    records, errors = parse_file(path)

    assert len(records) == 1
    assert len(errors)  == 1


def test_parse_file_all_invalid(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps([{"bad": "data"}, {"also": "bad"}]))
    records, errors = parse_file(path)

    assert records     == []
    assert len(errors) == 2


def test_parse_file_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not valid json {{{")
    records, errors = parse_file(path)

    assert records     == []
    assert len(errors) == 1
    assert "Invalid JSON" in errors[0]

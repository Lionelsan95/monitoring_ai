"""Integration tests — MetricRepository (SQLite in a temporary file)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from config import DBConfig
from domain.schemas import MetricRecord
from infrastructure.repository import MetricRepository


@pytest.fixture
def repo(tmp_path: Path) -> MetricRepository:
    return MetricRepository(DBConfig(path=str(tmp_path / "test.db")))


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def test_initial_count_is_zero(repo: MetricRepository) -> None:
    assert repo.count() == 0


def test_save_increments_count(repo: MetricRepository, sample_record: MetricRecord) -> None:
    repo.save(sample_record)
    assert repo.count() == 1


def test_save_batch(repo: MetricRepository, sample_record: MetricRecord) -> None:
    saved = repo.save_batch([sample_record, sample_record, sample_record])
    assert saved        == 3
    assert repo.count() == 3


def test_fetch_range_returns_record_in_range(
    repo: MetricRepository, sample_record: MetricRecord
) -> None:
    repo.save(sample_record)
    now     = _now()
    records = repo.fetch_range(start=now - timedelta(minutes=60), end=now)
    assert len(records) == 1
    assert records[0].cpu_usage == sample_record.cpu_usage


def test_fetch_range_excludes_records_before_start(
    repo: MetricRepository, sample_record: MetricRecord
) -> None:
    old = sample_record.model_copy(
        update={"timestamp": _now() - timedelta(hours=2)}
    )
    repo.save(old)
    now     = _now()
    records = repo.fetch_range(start=now - timedelta(minutes=60), end=now)
    assert records == []


def test_fetch_range_excludes_records_after_end(
    repo: MetricRepository, sample_record: MetricRecord
) -> None:
    future = sample_record.model_copy(
        update={"timestamp": _now() + timedelta(hours=1)}
    )
    repo.save(future)
    now     = _now()
    records = repo.fetch_range(start=now - timedelta(minutes=60), end=now)
    assert records == []


def test_fetch_range_explicit_bounds(
    repo: MetricRepository, sample_record: MetricRecord
) -> None:
    """fetch_range with fully explicit start and end — no dependency on wall clock."""
    anchor = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    inside  = sample_record.model_copy(update={"timestamp": anchor + timedelta(minutes=30)})
    outside = sample_record.model_copy(update={"timestamp": anchor - timedelta(minutes=30)})
    repo.save(inside)
    repo.save(outside)

    records = repo.fetch_range(start=anchor, end=anchor + timedelta(hours=1))
    assert len(records) == 1
    assert records[0].cpu_usage == inside.cpu_usage


def test_roundtrip_preserves_values(
    repo: MetricRepository, sample_record: MetricRecord
) -> None:
    repo.save(sample_record)
    now     = _now()
    records = repo.fetch_range(start=now - timedelta(minutes=60), end=now)
    assert records[0].cpu_usage            == sample_record.cpu_usage
    assert records[0].service_status.cache == sample_record.service_status.cache

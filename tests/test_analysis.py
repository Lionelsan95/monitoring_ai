"""Tests for the domain — analysis step."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.analysis import overall_health, run_analysis
from domain.schemas import Anomaly, AnomalyStatus, MetricRecord, Severity


_TS = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Mock detector — implements AnomalyDetectorPort, no LangChain, no prompt
# ---------------------------------------------------------------------------

class _MockDetector:
    def __init__(self, summary: str, anomalies: list[Anomaly]) -> None:
        self._summary   = summary
        self._anomalies = anomalies

    def detect(self, records: list[MetricRecord]) -> tuple[str, list[Anomaly]]:
        return self._summary, self._anomalies


# ---------------------------------------------------------------------------
# overall_health
# ---------------------------------------------------------------------------

def test_overall_health_no_anomaly() -> None:
    assert overall_health([]) == Severity.info


def test_overall_health_warning() -> None:
    anomaly = Anomaly(metric="cpu", value=80.0, threshold=75.0, severity=Severity.warning, description="high cpu", started_at=_TS, status=AnomalyStatus.active)
    assert overall_health([anomaly]) == Severity.warning


def test_overall_health_critical_dominates() -> None:
    anomalies = [
        Anomaly(metric="cpu",    value=95.0, threshold=90.0, severity=Severity.critical, description="critical cpu",    started_at=_TS, status=AnomalyStatus.active),
        Anomaly(metric="memory", value=80.0, threshold=75.0, severity=Severity.warning,  description="warning memory",  started_at=_TS, status=AnomalyStatus.active),
    ]
    assert overall_health(anomalies) == Severity.critical


# ---------------------------------------------------------------------------
# run_analysis
# ---------------------------------------------------------------------------

def test_run_analysis_returns_detector_output(sample_record: MetricRecord) -> None:
    anomaly  = Anomaly(metric="cpu_usage", value=92.0, threshold=90.0, severity=Severity.critical, description="high cpu", started_at=_TS, status=AnomalyStatus.active)
    detector = _MockDetector("All good.", [anomaly])

    result = run_analysis(records=[sample_record], detector=detector)

    assert result.summary      == "All good."
    assert result.record_count == 1
    assert len(result.anomalies) == 1
    assert result.anomalies[0].metric == "cpu_usage"


def test_run_analysis_derives_health_from_anomalies(sample_record: MetricRecord) -> None:
    critical = Anomaly(metric="cpu", value=95.0, threshold=90.0, severity=Severity.critical, description="x", started_at=_TS, status=AnomalyStatus.active)
    detector = _MockDetector("Critical state.", [critical])

    result = run_analysis(records=[sample_record], detector=detector)

    assert result.overall_health == Severity.critical


def test_run_analysis_healthy_when_no_anomalies(sample_record: MetricRecord) -> None:
    detector = _MockDetector("System stable.", [])

    result = run_analysis(records=[sample_record], detector=detector)

    assert result.anomalies    == []
    assert result.overall_health == Severity.info


def test_run_analysis_raises_on_empty_records() -> None:
    with pytest.raises(ValueError, match="No records"):
        run_analysis(records=[], detector=_MockDetector("", []))

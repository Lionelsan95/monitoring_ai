"""
Domain — analysis step.

Pure business logic: delegates anomaly detection to the injected detector,
then assembles the structured result. No LLM, no prompt, no JSON parsing here.
"""
from __future__ import annotations

from domain.ports import AnomalyDetectorPort
from domain.schemas import AnalysisResult, MetricRecord, Severity, Anomaly


def overall_health(anomalies: list[Anomaly]) -> Severity:
    """Derive the overall health status from the anomaly list."""
    if any(a.severity == Severity.critical for a in anomalies):
        return Severity.critical
    if any(a.severity == Severity.warning for a in anomalies):
        return Severity.warning
    return Severity.info


def run_analysis(
    records: list[MetricRecord],
    detector: AnomalyDetectorPort,
) -> AnalysisResult:
    """Detect anomalies over a set of records and return a structured result."""
    if not records:
        raise ValueError("No records to analyse in the requested window.")

    summary, anomalies = detector.detect(records)

    return AnalysisResult(
        window_start=min(r.timestamp for r in records),
        window_end=max(r.timestamp for r in records),
        record_count=len(records),
        anomalies=anomalies,
        summary=summary,
        overall_health=overall_health(anomalies),
    )

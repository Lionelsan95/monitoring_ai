"""Tests for the domain — recommendation step."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.recommendation import run_recommendation
from domain.schemas import Action, AnalysisResult, Priority, Severity

# ---------------------------------------------------------------------------
# Mock planner — implements ActionPlannerPort, no LangChain, no prompt
# ---------------------------------------------------------------------------

class _MockPlanner:
    def __init__(self, summary: str, actions: list[Action]) -> None:
        self._summary = summary
        self._actions = actions

    def plan(self, analysis: AnalysisResult) -> tuple[str, list[Action]]:
        return self._summary, self._actions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def healthy_analysis() -> AnalysisResult:
    now = datetime.now(tz=timezone.utc)
    return AnalysisResult(
        window_start=now,
        window_end=now,
        record_count=5,
        anomalies=[],
        summary="System stable.",
        overall_health=Severity.info,
    )


# ---------------------------------------------------------------------------
# run_recommendation
# ---------------------------------------------------------------------------

def test_run_recommendation_returns_planner_output(healthy_analysis: AnalysisResult) -> None:
    action  = Action(
        priority=Priority.low,
        category="monitoring",
        title="Continuous monitoring",
        description="Maintain current metric monitoring.",
        impact="Early anomaly detection.",
    )
    planner = _MockPlanner("No immediate action required.", [action])

    report = run_recommendation(healthy_analysis, planner)

    assert report.executive_summary == "No immediate action required."
    assert len(report.actions) == 1
    assert report.actions[0].priority == Priority.low


def test_run_recommendation_inherits_health(healthy_analysis: AnalysisResult) -> None:
    planner = _MockPlanner("OK", [])

    report = run_recommendation(healthy_analysis, planner)

    assert report.overall_health == Severity.info
    assert report.window_start   == healthy_analysis.window_start


def test_run_recommendation_propagates_anomalies(healthy_analysis: AnalysisResult) -> None:
    planner = _MockPlanner("Summary.", [])

    report = run_recommendation(healthy_analysis, planner)

    assert report.anomalies == healthy_analysis.anomalies

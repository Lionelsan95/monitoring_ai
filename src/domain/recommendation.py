"""
Domain — recommendation step.

Pure business logic: delegates action planning to the injected planner,
then assembles the final report. No LLM, no prompt, no JSON parsing here.
"""
from __future__ import annotations

from datetime import datetime, timezone

from domain.ports import ActionPlannerPort
from domain.schemas import AnalysisResult, Report


def run_recommendation(
    analysis: AnalysisResult,
    planner: ActionPlannerPort,
) -> Report:
    """Generate a prioritised action report from an AnalysisResult."""
    executive_summary, actions = planner.plan(analysis)

    return Report(
        generated_at=datetime.now(tz=timezone.utc),
        window_start=analysis.window_start,
        window_end=analysis.window_end,
        overall_health=analysis.overall_health,
        anomalies=analysis.anomalies,
        actions=actions,
        executive_summary=executive_summary,
    )

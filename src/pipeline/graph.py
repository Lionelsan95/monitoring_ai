"""
LangGraph pipeline — orchestration.

Single responsibility: wire the nodes and manage graph state.
No business logic, no prompts, no LLM config here.
Each node receives a ready-to-use port and delegates entirely to the domain.

The graph is compiled once (build_pipeline) then reused.
"""
from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph

from config import AppConfig
from domain.analysis import run_analysis
from domain.ports import AnomalyDetectorPort, ActionPlannerPort
from domain.recommendation import run_recommendation
from domain.schemas import AnalysisResult, MetricRecord, Report
from infrastructure.llm import build_detector, build_planner
from infrastructure.prompts import load_prompt


# ---------------------------------------------------------------------------
# State shared between nodes
# ---------------------------------------------------------------------------

class PipelineState(TypedDict, total=False):
    records:  list[MetricRecord]   # injected at entry
    analysis: AnalysisResult       # produced by the analysis node
    report:   Report               # produced by the recommendation node


# ---------------------------------------------------------------------------
# Node factories — receive a ready-to-use port, nothing else
# ---------------------------------------------------------------------------

def _make_analysis_node(detector: AnomalyDetectorPort):
    def node(state: PipelineState) -> PipelineState:
        return {"analysis": run_analysis(
            records=state["records"],
            detector=detector,
        )}
    return node


def _make_recommendation_node(planner: ActionPlannerPort):
    def node(state: PipelineState) -> PipelineState:
        return {"report": run_recommendation(
            analysis=state["analysis"],
            planner=planner,
        )}
    return node


# ---------------------------------------------------------------------------
# Graph construction — call once at startup
# ---------------------------------------------------------------------------

def build_pipeline(config: AppConfig, prompts_dir: Path | None = None):
    """
    Compile the LangGraph graph.
    Adapters are built here with models and prompts baked in.
    The result must be stored and reused (do not rebuild on every request).

    Graph: analyse → recommendation → END
    """
    pdir     = prompts_dir or config.prompts_dir
    detector = build_detector(config.llm.analysis,       load_prompt("analysis_system",       pdir))
    planner  = build_planner(config.llm.recommendation,  load_prompt("recommendation_system",  pdir))

    graph = StateGraph(PipelineState)
    graph.add_node("analyse",        _make_analysis_node(detector))
    graph.add_node("recommendation", _make_recommendation_node(planner))
    graph.set_entry_point("analyse")
    graph.add_edge("analyse",        "recommendation")
    graph.add_edge("recommendation", END)

    return graph.compile()

"""
Infrastructure LLM — specialised LangChain adapters.

Each adapter owns exactly one concern:
  - which model to call
  - which prompt to use
  - how to serialise inputs and parse outputs

The domain never sees any of this. It only calls detect() or plan().
This is the only file that imports LangChain.
"""
from __future__ import annotations

import json
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from config import LLMStepConfig
from domain.schemas import Action, AnalysisResult, Anomaly, MetricRecord, Priority


# ---------------------------------------------------------------------------
# Shared model factory
# ---------------------------------------------------------------------------

def _build_model(cfg: LLMStepConfig) -> BaseChatModel:
    if cfg.provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=cfg.model,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
    if cfg.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=cfg.model,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
    raise ValueError(
        f"Unknown LLM provider: '{cfg.provider}'. Supported: 'openai', 'anthropic'."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_fences(raw: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap around JSON."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


# ---------------------------------------------------------------------------
# Anomaly detector — implements AnomalyDetectorPort
# ---------------------------------------------------------------------------

class LangChainAnomalyDetector:
    """Calls the analysis LLM and parses its response into domain objects.

    Owns: model, system prompt, input serialisation, output parsing, fallback.
    """

    def __init__(self, model: BaseChatModel, system_prompt: str) -> None:
        self._model         = model
        self._system_prompt = system_prompt

    def detect(self, records: list[MetricRecord]) -> tuple[str, list[Anomaly]]:
        records_json = json.dumps(
            [r.model_dump(mode="json") for r in records], indent=2, default=str
        )
        user_content = f"Snapshots ({len(records)} records):\n{records_json}"

        raw = str(self._model.invoke([
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_content),
        ]).content)

        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> tuple[str, list[Anomaly]]:
        try:
            data      = json.loads(_strip_fences(raw))
            summary   = data.get("summary", "Analysis completed.")
            anomalies = [Anomaly(**a) for a in data.get("anomalies", [])]
            return summary, anomalies
        except (json.JSONDecodeError, TypeError):
            return "Analysis completed (partial LLM parsing).", []


# ---------------------------------------------------------------------------
# Action planner — implements ActionPlannerPort
# ---------------------------------------------------------------------------

class LangChainActionPlanner:
    """Calls the recommendation LLM and parses its response into domain objects.

    Owns: model, system prompt, input serialisation, output parsing, fallback.
    """

    def __init__(self, model: BaseChatModel, system_prompt: str) -> None:
        self._model         = model
        self._system_prompt = system_prompt

    def plan(self, analysis: AnalysisResult) -> tuple[str, list[Action]]:
        user_content = (
            f"Analysis result:\n"
            f"{json.dumps(analysis.model_dump(mode='json'), indent=2, default=str)}"
        )

        raw = str(self._model.invoke([
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_content),
        ]).content)

        return self._parse(raw, analysis)

    @staticmethod
    def _parse(raw: str, analysis: AnalysisResult) -> tuple[str, list[Action]]:
        try:
            data    = json.loads(_strip_fences(raw))
            summary = data.get("executive_summary", "Report generated.")
            actions = [Action(**a) for a in data.get("actions", [])]
            return summary, actions
        except (json.JSONDecodeError, TypeError):
            fallback = Action(
                priority=Priority.high,
                category="system",
                title="Investigate detected anomalies",
                description=(
                    f"{len(analysis.anomalies)} anomaly(ies) detected. "
                    "Check system logs and monitoring dashboards."
                ),
                impact="Identification and resolution of root causes.",
            )
            return "Partial report — LLM parsing failed.", [fallback]


# ---------------------------------------------------------------------------
# Public factories
# ---------------------------------------------------------------------------

def build_detector(cfg: LLMStepConfig, system_prompt: str) -> LangChainAnomalyDetector:
    """Instantiate an AnomalyDetector with its model and prompt baked in."""
    return LangChainAnomalyDetector(_build_model(cfg), system_prompt)


def build_planner(cfg: LLMStepConfig, system_prompt: str) -> LangChainActionPlanner:
    """Instantiate an ActionPlanner with its model and prompt baked in."""
    return LangChainActionPlanner(_build_model(cfg), system_prompt)

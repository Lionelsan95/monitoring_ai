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
import os
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
    if cfg.provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=cfg.model,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=cfg.temperature,
            num_predict=cfg.max_tokens,  # Ollama uses num_predict, not max_tokens
        )
    if cfg.provider == "bedrock":
        from langchain_aws import ChatBedrock
        # model must be the full Bedrock model ID, e.g.:
        #   anthropic.claude-3-5-sonnet-20241022-v2:0
        #   us.anthropic.claude-3-5-sonnet-20241022-v2:0  (cross-region inference)
        # No API key — credentials come from the IAM task role (ECS) or local AWS profile.
        return ChatBedrock(
            model_id=cfg.model,
            region_name=os.getenv("AWS_REGION", "eu-west-1"),
            model_kwargs={
                "temperature": cfg.temperature,
                "max_tokens":  cfg.max_tokens,
            },
        )
    raise ValueError(
        f"Unknown LLM provider: '{cfg.provider}'. "
        "Supported: 'openai', 'anthropic', 'ollama', 'bedrock'."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> dict:
    """Extract a JSON object from LLM output.

    Handles three common failure modes from open-weight models:
      1. Markdown code fences (```json ... ```)
      2. Prose preamble before the JSON block ("Here is the analysis:")
      3. Trailing text after the closing brace
    """
    text = raw.strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    # Fast path: the whole string is valid JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Slow path: extract outermost {...} block, tolerating surrounding prose
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())

    raise json.JSONDecodeError("No JSON object found in LLM response", text, 0)


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
            data      = _extract_json(raw)
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
            data    = _extract_json(raw)
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

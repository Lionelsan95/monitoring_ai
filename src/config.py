"""
Central application configuration.

Load order (lowest → highest priority):
  1. config.yaml  defaults section      — baseline for every node
  2. config.yaml  nodes.<name> section  — per-node overrides
  3. Environment variables              — secrets and paths only

The YAML file is controlled by CONFIG_PATH (env var, default: config.yaml).
Secrets stay in .env: OPENAI_API_KEY, ANTHROPIC_API_KEY, DB_PATH, PROMPTS_DIR.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

@dataclass
class LLMStepConfig:
    """LLM model configuration for a given pipeline step."""
    provider:    str
    model:       str
    temperature: float = 0.2
    max_tokens:  int   = 2048


@dataclass
class LLMConfig:
    analysis:       LLMStepConfig
    recommendation: LLMStepConfig


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

@dataclass
class DBConfig:
    path: str = "monitoring_ai.db"  # overridden by load_config()


# ---------------------------------------------------------------------------
# Global config
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    llm:         LLMConfig
    db:          DBConfig
    prompts_dir: Path


# ---------------------------------------------------------------------------
# Internal loaders
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resolve_node(defaults: dict, node_cfg: dict) -> LLMStepConfig:
    """Merge global YAML defaults with node-specific overrides."""
    merged = {**defaults, **node_cfg}
    if "provider" not in merged or "model" not in merged:
        raise ValueError(
            f"Node config is missing required fields 'provider' and/or 'model'. "
            f"Got: {merged}"
        )
    return LLMStepConfig(
        provider=merged["provider"],
        model=merged["model"],
        temperature=float(merged.get("temperature", 0.2)),
        max_tokens=int(merged.get("max_tokens", 2048)),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def load_config() -> AppConfig:
    """
    Load the full application configuration.

    Reads config.yaml (or CONFIG_PATH) for model settings.
    Reads environment variables for secrets (API keys, DB_PATH, PROMPTS_DIR).
    """
    config_path = Path(os.getenv("CONFIG_PATH", "config.yaml"))
    yaml_data   = _load_yaml(config_path)

    defaults = yaml_data.get("defaults", {})
    nodes    = yaml_data.get("nodes", {})

    # Anchor defaults to the project root (two levels above src/config.py)
    _root        = Path(__file__).parent.parent
    _default_db  = str(_root / "monitoring_ai.db")
    _default_prd = str(_root / "prompts")

    return AppConfig(
        llm=LLMConfig(
            analysis       = _resolve_node(defaults, nodes.get("analysis", {})),
            recommendation = _resolve_node(defaults, nodes.get("recommendation", {})),
        ),
        db          = DBConfig(path=os.getenv("DB_PATH", _default_db)),
        prompts_dir = Path(os.getenv("PROMPTS_DIR", _default_prd)),
    )

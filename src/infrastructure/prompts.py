"""
Infrastructure — prompt file loader.

Prompts are versioned .md files stored in the prompts/ directory.
The default path is resolved from the project root.
It can be overridden via the PROMPTS_DIR environment variable or AppConfig.prompts_dir.
"""
from __future__ import annotations

import os
from pathlib import Path

# Default path: <project_root>/prompts/
# Resolved from this file: src/infrastructure/ → ../.. → project root
_DEFAULT_DIR = Path(__file__).parent.parent.parent / "prompts"


def load_prompt(name: str, prompts_dir: Path | None = None) -> str:
    """
    Load the content of a prompt file by name (without extension).

    Args:
        name:        File name without extension, e.g. "analysis_system"
        prompts_dir: Prompts directory. If None, uses PROMPTS_DIR env var or the default.

    Raises:
        FileNotFoundError: if the file does not exist.
    """
    directory = prompts_dir or Path(os.getenv("PROMPTS_DIR", str(_DEFAULT_DIR)))
    path = directory / f"{name}.md"

    if not path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {path}\n"
            f"Make sure the directory '{directory}' contains '{name}.md'."
        )

    return path.read_text(encoding="utf-8").strip()

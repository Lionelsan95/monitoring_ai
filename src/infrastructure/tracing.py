"""
Infrastructure — LangSmith run configuration.

Builds a RunnableConfig that enriches every pipeline trace with
contextual metadata (time range, record count, environment tag).

Tracing is fully opt-in: if LANGCHAIN_TRACING_V2 is not set,
LangChain ignores the config and no data is sent anywhere.
"""
from __future__ import annotations

import os
from datetime import datetime

from langchain_core.runnables import RunnableConfig


def build_run_config(
    record_count:  int,
    start:         datetime,
    end:           datetime,
    window_minutes: int | None = None,
) -> RunnableConfig:
    """Return a RunnableConfig that annotates the pipeline run in LangSmith.

    Run name reflects the query mode:
      - Window mode: "analysis · 60min · 120 records"
      - Range mode:  "analysis · 10:00 → 11:00 · 120 records"
    """
    env = os.getenv("APP_ENV", "dev")

    if window_minutes is not None:
        run_name = f"analysis · {window_minutes}min · {record_count} records"
    else:
        run_name = f"analysis · {start:%H:%M} → {end:%H:%M} · {record_count} records"

    return RunnableConfig(
        run_name=run_name,
        tags=[env],
        metadata={
            "record_count": record_count,
            "environment":  env,
            "start":        start.isoformat(),
            "end":          end.isoformat(),
            **({"window_minutes": window_minutes} if window_minutes is not None else {}),
        },
    )

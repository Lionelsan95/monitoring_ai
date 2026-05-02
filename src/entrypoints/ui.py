"""
Streamlit entrypoint — dashboard UI.

Two tabs:
  Ingest  — upload a JSON metrics file and persist it to the database
  Analyze — pick a time window or explicit range, run the pipeline, read the report

Calls domain functions directly (same as the CLI). Does not go through the
FastAPI server — both can run independently.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import os

import streamlit as st

from config import load_config
from domain.ingestor import ingest_file
from domain.schemas import AnomalyStatus, Report, Severity
from infrastructure.repository import MetricRepository
from infrastructure.tracing import build_run_config
from pipeline.graph import build_pipeline


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Monitoring AI",
    page_icon="🖥️",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Shared resources — built once, reused across reruns
# ---------------------------------------------------------------------------

@st.cache_resource
def _load_resources():
    config   = load_config()
    repo     = MetricRepository(config.db)
    pipeline = build_pipeline(config)
    return repo, pipeline, config


# ---------------------------------------------------------------------------
# Helpers — report rendering
# ---------------------------------------------------------------------------

_HEALTH_COLOR = {
    Severity.critical: "🔴",
    Severity.warning:  "🟡",
    Severity.info:     "🟢",
}

_SEVERITY_COLOR = {
    Severity.critical: ":red[CRITICAL]",
    Severity.warning:  ":orange[WARNING]",
    Severity.info:     ":green[INFO]",
}

_STATUS_BADGE = {
    AnomalyStatus.active:    ":red[active]",
    AnomalyStatus.recovered: ":green[recovered]",
    AnomalyStatus.recurring: ":orange[recurring]",
}

_PRIORITY_COLOR = {
    "high":   ":red[HIGH]",
    "medium": ":orange[MEDIUM]",
    "low":    ":blue[LOW]",
}


def _render_report(report: Report) -> None:
    icon  = _HEALTH_COLOR.get(report.overall_health, "⚪")
    label = report.overall_health.value.upper()

    st.markdown(f"## {icon} Overall health: **{label}**")
    st.caption(
        f"Window: {report.window_start:%Y-%m-%d %H:%M} → "
        f"{report.window_end:%Y-%m-%d %H:%M} UTC  |  "
        f"Generated: {report.generated_at:%Y-%m-%d %H:%M} UTC"
    )

    st.markdown("### Executive summary")
    st.info(report.executive_summary)

    # Anomalies
    st.markdown("### Anomalies")
    if not report.anomalies:
        st.success("No anomalies detected in this window.")
    else:
        rows = []
        for a in report.anomalies:
            rows.append({
                "Metric":      a.metric,
                "Value":       str(a.value),
                "Threshold":   str(a.threshold),
                "Severity":    a.severity.value,
                "Status":      a.status.value,
                "Started at":  a.started_at.strftime("%H:%M"),
                "Resolved at": a.resolved_at.strftime("%H:%M") if a.resolved_at else "—",
                "Description": a.description,
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

    # Actions
    st.markdown("### Recommended actions")
    if not report.actions:
        st.success("No actions required.")
    else:
        for i, action in enumerate(report.actions, 1):
            priority_label = _PRIORITY_COLOR.get(action.priority.value, action.priority.value)
            with st.expander(f"{i}. {action.title}  —  {priority_label}  |  {action.category}"):
                st.markdown(f"**What to do:** {action.description}")
                st.markdown(f"**Expected impact:** {action.impact}")


# ---------------------------------------------------------------------------
# Tab — Ingest
# ---------------------------------------------------------------------------

def _tab_ingest(repo: MetricRepository) -> None:
    st.subheader("Ingest metrics from a JSON file")
    st.caption("Accepts a single JSON object or an array of metric records.")

    uploaded = st.file_uploader("Choose a JSON file", type=["json"])

    if uploaded and st.button("Ingest", type="primary"):
        with st.spinner("Ingesting…"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
                tmp.write(uploaded.read())
                tmp_path = Path(tmp.name)
            try:
                result = ingest_file(tmp_path, repo)
            finally:
                os.unlink(tmp_path)

        if result.errors == 0:
            st.success(f"Saved **{result.saved}** record(s) successfully.")
        else:
            st.warning(
                f"Saved **{result.saved}** record(s).  "
                f"**{result.errors}** record(s) failed validation."
            )
            for msg in result.messages:
                st.error(msg)

    st.divider()
    st.caption(f"Records currently in database: **{repo.count()}**")


# ---------------------------------------------------------------------------
# Tab — Analyze
# ---------------------------------------------------------------------------

def _tab_analyze(repo: MetricRepository, pipeline, config) -> None:
    st.subheader("Run the analysis pipeline")

    mode = st.radio(
        "Query mode",
        ["Rolling window", "Explicit range"],
        horizontal=True,
    )

    if mode == "Rolling window":
        window = st.slider("Window (minutes)", min_value=30, max_value=480, value=60, step=30)
        end   = datetime.now(tz=timezone.utc)
        start = end - timedelta(minutes=window)
        window_minutes = window
    else:
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start date", value=datetime.now(tz=timezone.utc).date())
            start_time = st.time_input("Start time (UTC)", value=datetime.now(tz=timezone.utc).replace(hour=10, minute=0, second=0).time())
        with col2:
            end_date = st.date_input("End date", value=datetime.now(tz=timezone.utc).date())
            end_time = st.time_input("End time (UTC)", value=datetime.now(tz=timezone.utc).replace(hour=11, minute=0, second=0).time())

        start = datetime.combine(start_date, start_time, tzinfo=timezone.utc)
        end   = datetime.combine(end_date,   end_time,   tzinfo=timezone.utc)
        window_minutes = None

        if start >= end:
            st.error("Start must be strictly before end.")
            return

    record_count = repo.count()
    st.caption(f"Records in database: **{record_count}**")

    if st.button("Analyse", type="primary"):
        records = repo.fetch_range(start, end)

        if not records:
            st.warning("No records found in the requested time range.")
            return

        st.info(f"Analysing **{len(records)}** record(s)…")

        with st.spinner("Running pipeline…"):
            run_cfg = build_run_config(
                len(records), start=start, end=end, window_minutes=window_minutes
            )
            state  = pipeline.invoke({"records": records}, run_cfg)
            report: Report = state["report"]

        _render_report(report)


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Monitoring AI")
    st.caption("LLM-assisted infrastructure analysis — ingest metrics, detect anomalies, get recommendations.")

    repo, pipeline, config = _load_resources()

    tab_ingest, tab_analyze = st.tabs(["Ingest", "Analyze"])

    with tab_ingest:
        _tab_ingest(repo)

    with tab_analyze:
        _tab_analyze(repo, pipeline, config)


if __name__ == "__main__":
    main()

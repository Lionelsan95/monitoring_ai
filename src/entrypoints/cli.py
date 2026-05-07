"""
CLI entrypoint (Click).

Available commands:
  monitoring-ai ingest --file <path>                         — ingest a JSON file
  monitoring-ai analyze [--window N]                         — rolling window
  monitoring-ai analyze --start <iso> --end <iso>            — explicit range
  monitoring-ai db stats                                     — display database statistics
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from config import load_config
from domain.ingestor import ingest_file, parse_file
from domain.schemas import AnalyzeParams, Report, Severity
from infrastructure.repository import MetricRepository
from infrastructure.tracing import build_run_config
from pipeline.graph import build_pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo_and_config():
    config = load_config()
    repo   = MetricRepository(config.db)
    return repo, config


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise click.BadParameter(
            f"'{value}' is not a valid ISO 8601 datetime. "
            "Expected format: 2024-01-15T10:00:00Z or 2024-01-15T10:00:00+00:00",
        )


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Monitoring AI — LLM-assisted infrastructure analysis."""


# ---------------------------------------------------------------------------
# monitoring-ai ingest
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--file", "-f", "filepath",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="JSON file to ingest (single object or array of records).",
)
def ingest(filepath: Path) -> None:
    """Ingest a JSON metrics file into the database."""
    repo, _ = _make_repo_and_config()
    result  = ingest_file(filepath, repo)

    click.echo(f"Saved: {result.saved}  |  Errors: {result.errors}")
    for msg in result.messages:
        click.echo(f"  ⚠  {msg}", err=True)

    sys.exit(0 if result.errors == 0 else 1)


# ---------------------------------------------------------------------------
# monitoring-ai analyze
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--file", "-f", "from_file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Analyse records from a JSON file without saving to the database.",
)
@click.option(
    "--window", "-w",
    default=60,
    show_default=True,
    help="Rolling window in minutes (minimum 30). Ignored if --start/--end or --file are set.",
)
@click.option(
    "--start",
    "start_str",
    default=None,
    help="Range start — ISO 8601 datetime, e.g. 2024-01-15T10:00:00Z.",
)
@click.option(
    "--end",
    "end_str",
    default=None,
    help="Range end   — ISO 8601 datetime, e.g. 2024-01-15T11:00:00Z.",
)
@click.option(
    "--output", "-o",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format.",
)
def analyze(  # noqa: PLR0912
    from_file: Path | None,
    window: int,
    start_str: str | None,
    end_str: str | None,
    output: str,
) -> None:
    """Run the analysis pipeline over recent records.

    \b
    Examples:
      # Analyse a file directly (no DB write)
      monitoring-ai analyze --file metrics.json

      # Rolling window (default 60 min)
      monitoring-ai analyze --window 30

      # Explicit range
      monitoring-ai analyze --start 2024-01-15T10:00:00Z --end 2024-01-15T11:00:00Z
    """
    _, config = _make_repo_and_config()
    pipeline  = build_pipeline(config)

    if from_file:
        records, errors = parse_file(from_file)
        if errors:
            for msg in errors:
                click.echo(f"  ⚠  {msg}", err=True)
        if not records:
            click.echo("No valid records in file.", err=True)
            sys.exit(1)

        start = min(r.timestamp for r in records)
        end   = max(r.timestamp for r in records)
        click.echo(f"Analysing {len(records)} record(s) from file...", err=True)

        state          = pipeline.invoke(
            {"records": records},
            build_run_config(len(records), start=start, end=end),
        )
        report: Report = state["report"]

    else:
        # Parse and validate params — reuse the same Pydantic model as the API
        try:
            params = AnalyzeParams(
                window_minutes=window,
                start=_parse_iso(start_str),
                end=_parse_iso(end_str),
            )
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc

        repo, _ = _make_repo_and_config()

        if params.start and params.end:
            start, end     = params.start, params.end
            window_minutes = None
        else:
            end            = datetime.now(tz=timezone.utc)
            start          = end - timedelta(minutes=params.window_minutes)
            window_minutes = params.window_minutes

        records = repo.fetch_range(start, end)
        if not records:
            click.echo("No records found in the requested time range.", err=True)
            sys.exit(1)

        click.echo(f"Analysing {len(records)} record(s)...", err=True)

        state          = pipeline.invoke(
            {"records": records},
            build_run_config(len(records), start=start, end=end, window_minutes=window_minutes),
        )
        report: Report = state["report"]

    if output == "json":
        click.echo(report.model_dump_json(indent=2))
    else:
        _print_report(report)


# ---------------------------------------------------------------------------
# monitoring-ai db
# ---------------------------------------------------------------------------

@cli.group()
def db() -> None:
    """Database management commands."""


@db.command("stats")
def db_stats() -> None:
    """Display database statistics."""
    repo, config = _make_repo_and_config()
    click.echo(f"Database      : {config.db.path}")
    click.echo(f"Total records : {repo.count()}")


# ---------------------------------------------------------------------------
# Text report rendering
# ---------------------------------------------------------------------------

_SEVERITY_COLOR = {
    Severity.critical: "red",
    Severity.warning:  "yellow",
    Severity.info:     "green",
}

_PRIORITY_COLOR = {"high": "red", "medium": "yellow", "low": "green"}


def _print_report(report: Report) -> None:
    color = _SEVERITY_COLOR.get(report.overall_health, "white")

    click.echo(f"\n{'═' * 62}")
    click.echo(click.style(
        f"  Overall health: {report.overall_health.value.upper()}",
        fg=color, bold=True,
    ))
    click.echo(
        f"  Window        : {report.window_start:%Y-%m-%d %H:%M}"
        f" → {report.window_end:%Y-%m-%d %H:%M} UTC"
    )
    click.echo(f"{'═' * 62}\n")

    click.echo(f"Executive summary:\n  {report.executive_summary}\n")

    if report.anomalies:
        click.echo("Anomalies:")
        for a in report.anomalies:
            c = _SEVERITY_COLOR.get(a.severity, "white")
            click.echo(f"  [{click.style(a.severity.value.upper(), fg=c)}] {a.description}")

    if report.actions:
        click.echo("\nRecommended actions:")
        for i, action in enumerate(report.actions, 1):
            c = _PRIORITY_COLOR.get(action.priority.value, "white")
            priority = click.style(action.priority.value.upper(), fg=c)
            click.echo(f"\n  {i}. [{priority}] {action.title}")
            click.echo(f"     Category : {action.category}")
            click.echo(f"     {action.description}")
            click.echo(f"     Impact   : {action.impact}")

    click.echo("")

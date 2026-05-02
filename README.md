# Monitoring AI

AI-powered infrastructure monitoring pipeline. Ingests system metric snapshots, detects anomalies via LLM analysis, and generates prioritised action recommendations.

---

## What it does

1. **Ingest** — accepts metric snapshots (CPU, memory, disk, latency, error rate, …) via REST API or CLI, validates them, and persists them in SQLite.
2. **Analyse** — runs a LangGraph pipeline that sends the full time series to an LLM, which identifies anomalies, anchors each one to its exact timestamp, and classifies whether it is still active, self-resolved, or recurring.
3. **Recommend** — a second LLM step takes the analysis result and produces a prioritised list of concrete remediation steps, framed differently depending on whether the anomaly is still live, already recovered, or showing a recurring pattern.
4. **Report** — the final report (overall health, timestamped anomalies, status-aware actions, executive summary) is returned as structured JSON, rendered as a coloured CLI table, or displayed in an interactive web dashboard.
5. **Trace** — every pipeline run is traced in LangSmith with per-node latency, token usage, and full LLM input/output (opt-in via env var).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Entrypoints                                                │
│  FastAPI  (/ingest  /ingest/file  /analyze  /health)        │
│  Click CLI  (ingest  analyze  db stats)                     │
│  Streamlit  (Ingest tab  /  Analyze tab)                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Domain  (pure Python — zero infrastructure imports)        │
│                                                             │
│  ingestor.py          validate & batch-persist records      │
│  analysis.py          call detector → AnalysisResult        │
│  recommendation.py    call planner  → Report                │
│  schemas.py           Pydantic contracts between modules    │
│  ports.py             AnomalyDetectorPort                   │
│                       ActionPlannerPort                     │
│                       RepositoryPort                        │
└──────┬───────────────────────────────────────┬──────────────┘
       │                                       │
┌──────▼──────────────┐             ┌──────────▼──────────────┐
│  Infrastructure     │             │  Pipeline               │
│                     │             │                         │
│  llm.py             │             │  graph.py               │
│  LangChainAnomaly   │             │  LangGraph              │
│  Detector           │             │  analyse → recommend    │
│  LangChainAction    │             └─────────────────────────┘
│  Planner            │
│                     │
│  repository.py      │
│  SQLite             │
│                     │
│  prompts.py         │
│  load .md files     │
│                     │
│  tracing.py         │
│  LangSmith config   │
└─────────────────────┘
```

**Key design decisions:**

- **Hexagonal architecture** — the domain never imports LangChain, SQLite, or FastAPI. Swapping any infrastructure component touches only one file.
- **Specialised ports** — `AnomalyDetectorPort` and `ActionPlannerPort` speak in domain terms (`detect(records)`, `plan(analysis)`). The domain cannot be called with the wrong prompt; prompt management is entirely an adapter concern. Tests use `_MockDetector` / `_MockPlanner` that return domain objects directly — no JSON, no LLM.
- **LangGraph pipeline** — compiled once at startup and reused across requests. Adding a new step means adding a node and an edge, nothing else.
- **YAML config** — model provider, model name, temperature, and max tokens are set in `config.yaml`. No Python changes needed to switch models.
- **Versioned prompts** — system prompts live in `prompts/*.md`, tracked by git. Prompt engineering requires no code change.
- **LangSmith tracing** — every pipeline run is automatically traced when `LANGCHAIN_TRACING_V2=true`. Each run is annotated with the time range, record count, and environment tag.
- **Flexible time range** — `POST /analyze` and `monitoring-ai analyze` support both a rolling window (`window_minutes`) and an explicit `start`/`end` datetime range. The same Pydantic validator enforces correctness in both entrypoints.
- **Temporal anomaly classification** — each detected anomaly is anchored to its exact first occurrence timestamp and classified as `active` (still ongoing), `recovered` (self-resolved within the window), or `recurring` (appeared, recovered, appeared again). Recommendations are framed accordingly: active anomalies get immediate mitigation steps, recovered ones get preventive actions, recurring ones get root-cause investigation guidance.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Package manager | [uv](https://github.com/astral-sh/uv) |
| Data validation | Pydantic v2 |
| LLM orchestration | LangGraph + LangChain Core |
| LLM providers | OpenAI (`langchain-openai`), Anthropic (`langchain-anthropic`) |
| Observability | LangSmith (`langsmith`) |
| REST API | FastAPI + Uvicorn |
| CLI | Click |
| Web UI | Streamlit (optional) |
| Persistence | SQLite (stdlib `sqlite3`) |
| Configuration | PyYAML + python-dotenv |
| Testing | pytest + pytest-asyncio |

---

## Project structure

```
monitoring_ai/
├── config.yaml                  # LLM model config (provider, model, temperature)
├── .env                         # Secrets — API keys, DB path  (not committed)
├── .env.example                 # Template for .env
├── pyproject.toml
├── main.py                      # Convenience entry: python main.py
│
├── prompts/
│   ├── analysis_system.md       # System prompt for the analysis LLM step
│   └── recommendation_system.md # System prompt for the recommendation LLM step
│
├── src/
│   ├── config.py                # Load config.yaml + env vars → AppConfig
│   │
│   ├── domain/
│   │   ├── schemas.py           # MetricRecord, AnalysisResult, Report, … (Pydantic)
│   │   ├── ports.py             # AnomalyDetectorPort, ActionPlannerPort, RepositoryPort
│   │   ├── analysis.py          # run_analysis(records, detector) → AnalysisResult
│   │   ├── recommendation.py    # run_recommendation(analysis, planner) → Report
│   │   └── ingestor.py          # ingest_records() / ingest_file()
│   │
│   ├── infrastructure/
│   │   ├── llm.py               # LangChainAnomalyDetector, LangChainActionPlanner
│   │   ├── repository.py        # MetricRepository (SQLite)
│   │   ├── prompts.py           # load_prompt() — reads prompts/*.md
│   │   └── tracing.py           # build_run_config() — LangSmith run metadata
│   │
│   ├── pipeline/
│   │   └── graph.py             # build_pipeline() — compiles the LangGraph graph
│   │
│   └── entrypoints/
│       ├── api.py               # FastAPI app
│       ├── cli.py               # Click CLI
│       └── ui.py                # Streamlit dashboard (optional)
│
└── tests/
    ├── conftest.py
    ├── test_analysis.py
    ├── test_recommendation.py
    ├── test_ingestor.py
    └── test_repository.py
```

---

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- At least one API key: OpenAI and/or Anthropic, depending on the models set in `config.yaml`

---

## Setup

**1. Clone and install**

```bash
git clone <repo-url>
cd monitoring_ai
uv sync --extra dev        # API + CLI + tests
uv sync --extra ui         # add Streamlit dashboard
uv sync --extra dev --extra ui  # everything
```

**2. Configure secrets**

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

**3. Configure models** (optional)

`config.yaml` controls which model runs each pipeline step. Edit it to switch providers or models without touching any Python:

```yaml
defaults:
  temperature: 0.2
  max_tokens: 2048

nodes:
  analysis:
    provider: openai       # openai | anthropic
    model: gpt-4o
    temperature: 0.2

  recommendation:
    provider: anthropic
    model: claude-sonnet-4-6
    temperature: 0.3
```

Any field set under a node overrides the global `defaults`.

---

## Configuration reference

### `config.yaml`

| Key | Description |
|---|---|
| `defaults.temperature` | Fallback temperature for all nodes |
| `defaults.max_tokens` | Fallback max tokens for all nodes |
| `nodes.<name>.provider` | `openai` or `anthropic` |
| `nodes.<name>.model` | Model identifier (e.g. `gpt-4o`, `claude-sonnet-4-6`) |
| `nodes.<name>.temperature` | Override temperature for this node |
| `nodes.<name>.max_tokens` | Override max tokens for this node |

To use a different YAML per environment, set `CONFIG_PATH` in `.env`:

```env
CONFIG_PATH=config.prod.yaml
```

### `.env` — secrets and environment settings

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | — |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `DB_PATH` | Path to the SQLite database file | `monitoring_ai.db` |
| `CONFIG_PATH` | Path to the YAML config file | `config.yaml` |
| `PROMPTS_DIR` | Path to the prompts directory | `prompts/` |
| `APP_ENV` | Environment tag attached to LangSmith traces | `dev` |
| `LANGCHAIN_TRACING_V2` | Set to `true` to enable LangSmith tracing | off |
| `LANGCHAIN_API_KEY` | LangSmith API key | — |
| `LANGCHAIN_PROJECT` | LangSmith project name | — |

---

## Running

### REST API

```bash
uv run uvicorn entrypoints.api:app --reload
```

Available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### CLI

```bash
uv run monitoring-ai --help
```

### Streamlit dashboard

```bash
uv run streamlit run src/entrypoints/ui.py
```

Available at `http://localhost:8501`. Requires the `ui` extra (`uv sync --extra ui`).

The dashboard and the REST API are fully independent — neither requires the other to be running.

---

## API reference

### `GET /health`

Returns the service status and number of records in the database.

```json
{"status": "ok", "records_in_db": 42}
```

---

### `POST /ingest`

Ingest one or more metric records from a JSON body.

**Request:**

```json
{
  "records": [
    {
      "timestamp": "2024-01-15T10:30:00Z",
      "cpu_usage": 85.2,
      "memory_usage": 72.1,
      "latency_ms": 245.0,
      "disk_usage": 68.5,
      "network_in_kbps": 1500.0,
      "network_out_kbps": 800.0,
      "io_wait": 3.5,
      "thread_count": 120,
      "active_connections": 350,
      "error_rate": 0.02,
      "uptime_seconds": 86400,
      "temperature_celsius": 65.0,
      "power_consumption_watts": 250.0,
      "service_status": {
        "database": "online",
        "api_gateway": "online",
        "cache": "degraded"
      }
    }
  ]
}
```

**Response:**

```json
{"saved": 1, "errors": 0, "messages": []}
```

Invalid records are skipped and counted in `errors`; valid ones are saved. A 422 is returned only when every record failed validation.

---

### `POST /ingest/file`

Ingest records from an uploaded JSON file (single object or array).

```bash
curl -X POST http://localhost:8000/ingest/file \
  -F "file=@metrics.json"
```

---

### `POST /analyze`

Run the full analysis + recommendation pipeline. Supports two mutually exclusive query modes.

**Mode 1 — rolling window (default)**

```json
{"window_minutes": 60}
```

`window_minutes` must be ≥ 30. Defaults to 60. The window is computed backwards from the moment the request is received.

**Mode 2 — explicit range**

```json
{
  "start": "2024-01-15T10:00:00Z",
  "end":   "2024-01-15T11:00:00Z"
}
```

Both `start` and `end` are required together (one without the other returns 422). `start` must be strictly before `end`. Datetimes must be ISO 8601 with timezone.

**Validation rules:**
- Providing only `start` or only `end` → 422
- `start >= end` → 422
- No records in the requested range → 404

**Response:**

```json
{
  "generated_at": "2024-01-15T11:05:00Z",
  "window_start": "2024-01-15T10:00:00Z",
  "window_end":   "2024-01-15T11:00:00Z",
  "overall_health": "critical",
  "anomalies": [
    {
      "metric": "cpu_usage",
      "value": 93.0,
      "threshold": 85.0,
      "severity": "critical",
      "description": "CPU spiked to 93 % at 10:00, then recovered to normal levels by 10:30.",
      "started_at": "2024-01-15T10:00:00Z",
      "resolved_at": "2024-01-15T10:30:00Z",
      "status": "recovered"
    },
    {
      "metric": "service_status",
      "value": "degraded",
      "threshold": "online",
      "severity": "critical",
      "description": "API gateway degraded at 10:00, recovered at 10:30, then degraded again at 10:45 — still ongoing.",
      "started_at": "2024-01-15T10:00:00Z",
      "resolved_at": null,
      "status": "recurring"
    }
  ],
  "actions": [
    {
      "priority": "high",
      "category": "service_status",
      "title": "Restart API gateway — active recurring degradation",
      "description": "Run `systemctl restart api-gateway` and tail logs with `journalctl -fu api-gateway`. This is the second episode within the hour — check for OOM kills or connection pool exhaustion in the logs before restarting.",
      "impact": "Restores gateway availability; log inspection reveals whether this is a resource leak or an upstream dependency issue."
    },
    {
      "priority": "medium",
      "category": "cpu",
      "title": "Add CPU alert at 85 % — spike self-resolved but left no alert",
      "description": "Configure an alert rule in your monitoring system to page on-call when cpu_usage > 85 % for more than 2 consecutive minutes.",
      "impact": "Ensures the next similar spike is caught proactively rather than discovered retrospectively."
    }
  ],
  "executive_summary": "A critical CPU spike occurred at 10:00 and self-resolved within 30 minutes, but the API gateway has been cycling between degraded and online states — it is currently degraded for the second time this hour. Immediate gateway intervention is required; the CPU event warrants an alerting rule to prevent silent recurrence."
}
```

**Anomaly status values:**

| Status | Meaning | Recommendation framing |
|---|---|---|
| `active` | Anomaly is still present at `window_end` | Immediate mitigation — high priority, imperative actions |
| `recovered` | Anomaly appeared then self-resolved within the window | Preventive — add alerting, identify the trigger |
| `recurring` | Appeared, recovered, appeared again | Root cause investigation — not just symptom relief |

---

## CLI reference

### `monitoring-ai ingest`

Ingest a local JSON file into the database.

```bash
uv run monitoring-ai ingest --file metrics.json
uv run monitoring-ai ingest -f /path/to/batch.json
```

The file can be a single JSON object or a JSON array of records. Invalid records are skipped and reported; valid ones are saved. Exits with code 1 if any errors occurred.

### `monitoring-ai analyze`

Run the pipeline over recent records. Supports the same two modes as the API.

```bash
# Rolling window — default 60 min
uv run monitoring-ai analyze

# Custom window
uv run monitoring-ai analyze --window 30

# Explicit range (ISO 8601, timezone required)
uv run monitoring-ai analyze --start 2024-01-15T10:00:00Z --end 2024-01-15T11:00:00Z

# JSON output (pipe-friendly)
uv run monitoring-ai analyze --window 30 --output json
uv run monitoring-ai analyze --start 2024-01-15T10:00:00Z --end 2024-01-15T11:00:00Z --output json
```

| Flag | Default | Description |
|---|---|---|
| `--window`, `-w` | `60` | Rolling window in minutes (min 30). Ignored if `--start`/`--end` are set. |
| `--start` | — | Range start — ISO 8601 datetime, e.g. `2024-01-15T10:00:00Z` |
| `--end` | — | Range end   — ISO 8601 datetime, e.g. `2024-01-15T11:00:00Z` |
| `--output`, `-o` | `text` | Output format: `text` or `json` |

`--start` and `--end` must always be provided together.

### `monitoring-ai db stats`

Display the database path and total record count.

```bash
uv run monitoring-ai db stats
```

---

## Streamlit UI reference

```bash
uv run streamlit run src/entrypoints/ui.py
```

The dashboard exposes two tabs.

### Ingest tab

- Drag-and-drop (or click to browse) a JSON metrics file — single object or array.
- Press **Ingest** to validate and persist. Results show saved / error counts.
- A live record count is displayed at the bottom.

### Analyze tab

**Rolling window mode** — a slider from 30 to 480 minutes, computed back from now.

**Explicit range mode** — separate date and time pickers for start and end (UTC).

Press **Analyse** to run the pipeline. The report renders inline:

| Section | Content |
|---|---|
| Overall health | Colour-coded indicator (🟢 info / 🟡 warning / 🔴 critical) |
| Executive summary | 2–3 sentence synthesis from the LLM |
| Anomaly table | Metric, value, threshold, severity, status, started\_at, resolved\_at |
| Action list | Collapsible expanders per action, coloured by priority |

Anomaly status colours: `active` = red, `recovered` = green, `recurring` = orange.

The dashboard calls domain functions directly — the FastAPI server does not need to be running.

### Removing the UI

Delete `src/entrypoints/ui.py` and remove the `ui` extra from `pyproject.toml`. Nothing else is affected.

---

## Observability — LangSmith

LangSmith traces are **opt-in** and require no code changes to enable or disable.

**Enable tracing:**

```env
APP_ENV=production
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=monitoring_ai_prod
```

**Per-environment projects** — use a different `LANGCHAIN_PROJECT` in each `.env` file to keep dev and prod traces separate:

```env
# .env.dev
LANGCHAIN_PROJECT=monitoring_ai_dev

# .env.prod
LANGCHAIN_PROJECT=monitoring_ai_prod
```

**What each trace shows:**

| Signal | Detail |
|---|---|
| Run name | Window mode: `analysis · 60min · 120 records` / Range mode: `analysis · 10:00 → 11:00 · 120 records` |
| Tags | environment (`dev`, `production`, …) |
| Metadata | `record_count`, `environment`, `start`, `end`, and `window_minutes` when in window mode |
| Node breakdown | latency and token usage per LangGraph node |
| LLM calls | full system prompt, user content, and raw response |
| Errors | exceptions surfaced at the node that raised them |

When `LANGCHAIN_TRACING_V2` is absent or `false`, the `RunnableConfig` passed to the pipeline is silently ignored — zero performance cost, zero data sent.

---

## Running tests

Tests run entirely offline — no real LLM calls, no external services, no LangSmith connection.

```bash
uv run pytest                         # all tests
uv run pytest -v                      # verbose
uv run pytest tests/test_analysis.py  # single file
```

The test suite uses:
- `_MockDetector` — implements `AnomalyDetectorPort`, returns controlled `(summary, anomalies)` tuples
- `_MockPlanner` — implements `ActionPlannerPort`, returns controlled `(summary, actions)` tuples
- `tmp_path` (pytest built-in) — SQLite tests use a throwaway database file

Because the ports are expressed in domain terms, mocks return domain objects directly. There is no JSON to craft, no LLM response to fake.

---

## Extending the project

### Add a new LLM provider

1. Open `src/infrastructure/llm.py`
2. Add a branch in `_build_model()` for the new provider
3. Install the corresponding LangChain integration package
4. Use the new provider name in `config.yaml` — nothing else changes

### Add a new pipeline step

1. Define a new port in `src/domain/ports.py` (in domain terms, not LLM terms)
2. Write a pure domain function in `src/domain/` that calls the port
3. Implement a LangChain adapter in `src/infrastructure/llm.py` that owns the model, prompt, and parsing
4. Add a node factory in `src/pipeline/graph.py` and wire it with `add_node()` / `add_edge()`
5. Add the new node under `nodes:` in `config.yaml`
6. Optionally add a prompt file in `prompts/`

### Tune analysis or recommendation behaviour

Edit `prompts/analysis_system.md` or `prompts/recommendation_system.md` directly. Prompts are loaded at startup — restart the service to pick up changes. No Python modifications required.

### Switch models per environment

```bash
# Development
CONFIG_PATH=config.dev.yaml uv run uvicorn entrypoints.api:app

# Production
CONFIG_PATH=config.prod.yaml uv run uvicorn entrypoints.api:app
```

---

## MetricRecord schema

| Field | Type | Constraints | Description |
|---|---|---|---|
| `timestamp` | datetime | ISO 8601 | Snapshot time (UTC recommended) |
| `cpu_usage` | float | 0 – 100 | CPU usage percentage |
| `memory_usage` | float | 0 – 100 | Memory usage percentage |
| `latency_ms` | float | ≥ 0 | API or service response latency |
| `disk_usage` | float | 0 – 100 | Disk usage percentage |
| `network_in_kbps` | float | ≥ 0 | Inbound network throughput |
| `network_out_kbps` | float | ≥ 0 | Outbound network throughput |
| `io_wait` | float | 0 – 100 | I/O wait percentage |
| `thread_count` | int | ≥ 0 | Number of active threads |
| `active_connections` | int | ≥ 0 | Number of active connections |
| `error_rate` | float | 0 – 1 | Error rate as a decimal (0.05 = 5 %) |
| `uptime_seconds` | int | ≥ 0 | Process or system uptime |
| `temperature_celsius` | float | ≥ 0 | Hardware temperature |
| `power_consumption_watts` | float | ≥ 0 | Power draw |
| `service_status.database` | enum | online / degraded / offline | |
| `service_status.api_gateway` | enum | online / degraded / offline | |
| `service_status.cache` | enum | online / degraded / offline | |

## Anomaly schema

Each anomaly in the report carries the following fields:

| Field | Type | Description |
|---|---|---|
| `metric` | string | Name of the affected metric (e.g. `cpu_usage`, `service_status`) |
| `value` | number or string | Observed value at the time of the anomaly |
| `threshold` | number or string | Reference value the LLM used to identify the anomaly |
| `severity` | `critical` / `warning` / `info` | Severity assigned by the LLM |
| `description` | string | Human-readable explanation of the anomaly |
| `started_at` | datetime | Timestamp of the first occurrence in the analysed window |
| `resolved_at` | datetime or null | Timestamp of resolution, or `null` if still active at `window_end` |
| `status` | `active` / `recovered` / `recurring` | Current state of the anomaly (see table in API reference) |

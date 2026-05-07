.DEFAULT_GOAL := help

PYTHON := uv run
IMAGE  := monitoring-ai

# ── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Setup ─────────────────────────────────────────────────────────────────────
.PHONY: install install-all

install: ## Install dev + UI + Ollama extras (local dev baseline)
	uv sync --extra dev --extra ui --extra ollama

install-all: ## Install all extras including cloud providers
	uv sync --extra dev --extra ui --extra ollama --extra openai --extra anthropic

# ── Quality ───────────────────────────────────────────────────────────────────
.PHONY: lint format check test

lint: ## Run ruff linter
	$(PYTHON) ruff check src/ tests/

format: ## Format code with ruff
	$(PYTHON) ruff format src/ tests/

check: lint test ## Run lint then tests

test: ## Run the full test suite
	$(PYTHON) pytest -v

# ── Local servers ─────────────────────────────────────────────────────────────
.PHONY: api ui

api: ## Start the FastAPI server (dev mode with reload)
	$(PYTHON) uvicorn entrypoints.api:app --reload

ui: ## Start the Streamlit dashboard
	$(PYTHON) streamlit run src/entrypoints/ui.py

# ── CLI shortcuts ─────────────────────────────────────────────────────────────
.PHONY: ingest analyze analyze-file analyze-range db-stats

ingest: ## Ingest a metrics file  → make ingest FILE=metrics.json
	$(PYTHON) monitoring-ai ingest -f $(FILE)

analyze: ## Rolling-window analysis  → make analyze [WINDOW=60]
	$(PYTHON) monitoring-ai analyze --window $(or $(WINDOW),60)

analyze-file: ## Analyse a file without saving  → make analyze-file FILE=metrics.json
	$(PYTHON) monitoring-ai analyze -f $(FILE)

analyze-range: ## Explicit range  → make analyze-range START=2024-01-15T10:00:00Z END=2024-01-15T11:00:00Z
	$(PYTHON) monitoring-ai analyze --start $(START) --end $(END)

db-stats: ## Show database statistics
	$(PYTHON) monitoring-ai db stats

# ── Docker ────────────────────────────────────────────────────────────────────
.PHONY: docker-build docker-up docker-down docker-logs docker-shell ollama-pull

docker-build: ## Build the Docker image
	docker build -t $(IMAGE) .

docker-up: ## Start all compose services (api + ui + ollama)
	docker compose up -d

docker-down: ## Stop and remove compose services
	docker compose down

docker-logs: ## Follow compose logs (Ctrl-C to stop)
	docker compose logs -f

docker-shell: ## Open a bash shell in the running api container
	docker compose exec api /bin/bash

ollama-pull: ## Pull the default model into the running Ollama container
	docker compose exec ollama ollama pull llama3.2:3b

# ── Housekeeping ──────────────────────────────────────────────────────────────
.PHONY: clean

clean: ## Remove Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

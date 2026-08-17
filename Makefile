# AgentFactory — canonical developer commands.
#
# The one command you need for local testing is `make studio` (or
# `agentfactory studio`): it builds the Studio UI if needed and serves the
# API + dashboard on http://localhost:8000 in a single process.

.PHONY: setup studio ui build-ui test typecheck lint security webcheck help

setup: ## Install Python + web dependencies (first time only)
	pip install -e . --no-build-isolation
	cd web && bun install

studio: ## Run the full platform (API + Studio UI) on http://localhost:8000
	agentfactory studio

ui: ## Run the Studio UI in dev mode (Vite :5173, proxies /api to :8000)
	cd web && bun run dev

build-ui: ## Build the Studio SPA into web/dist
	cd web && bun run build

test: ## Backend tests + coverage gate (≥80%)
	python -m pytest tests/ -q --cov

typecheck: ## mypy on the platform surface (the CI gate)
	python -m mypy agentfactory/app agentfactory/runtime.py agentfactory/terminal.py \
	  agentfactory/validation.py agentfactory/custom_tools.py \
	  agentfactory/crypto.py agentfactory/redact.py \
	  --follow-imports=skip --ignore-missing-imports

lint: ## Undefined-name lint (real bugs)
	python -m ruff check --select F821 agentfactory tests

security: ## Static security scans
	python -m bandit -r agentfactory -q -ll
	pip-audit -r requirements.txt

webcheck: ## UI typecheck + production build
	cd web && bun tsc -b --noEmit && bun run build

help: ## Show all targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

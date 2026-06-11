# RJourney Acquisitions Platform — developer commands (see CLAUDE.md §Commands).
# Backend deps via uv (apps/api); frontend via pnpm (apps/web); migrations at repo root.

VENV       := .venv
PY         := $(VENV)/bin/python
PYBIN      := $(VENV)/bin
API_DIR    := apps/api
WEB_DIR    := apps/web
OPENAPI    := $(WEB_DIR)/openapi.json

.DEFAULT_GOAL := help
.PHONY: help bootstrap dev down migrate migration seed openapi gen-types \
        test test-api test-web lint lint-api lint-web format e2e clean deploy-provision

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Install all deps (uv + pnpm) and pre-commit hooks
	uv venv --python 3.12 $(VENV)
	uv pip install --python $(PY) -e "$(API_DIR)[dev]"
	uv pip install --python $(PY) pre-commit
	cd $(WEB_DIR) && pnpm install
	$(PYBIN)/pre-commit install || true
	@echo "Bootstrap complete. Copy .env.example -> .env and fill it in."

dev: ## Run api + web + workers + infra via docker-compose
	docker compose up --build

down: ## Stop docker-compose stack
	docker compose down

migrate: ## Apply database migrations (alembic upgrade head)
	$(PYBIN)/alembic upgrade head

migration: ## Autogenerate a revision: make migration m="message"
	$(PYBIN)/alembic revision --autogenerate -m "$(m)"

seed: ## Load reference data (GL chart §8.5 + gate questions)
	$(PY) -m rjacq.seeds.load

openapi: ## Export the OpenAPI schema for the frontend contract
	$(PY) -m rjacq.openapi $(OPENAPI)

gen-types: openapi ## Regenerate frontend TypeScript types from the contract
	cd $(WEB_DIR) && pnpm gen:types

test: test-api test-web ## Run all tests

test-api: ## Backend tests (pytest, real Postgres)
	cd $(API_DIR) && ../../$(PYBIN)/pytest

test-web: ## Frontend tests (vitest)
	cd $(WEB_DIR) && pnpm test

lint: lint-api lint-web ## Lint everything (ruff, mypy, eslint, prettier)

lint-api:
	cd $(API_DIR) && ../../$(PYBIN)/ruff check rjacq tests
	cd $(API_DIR) && ../../$(PYBIN)/ruff format --check rjacq tests
	cd $(API_DIR) && ../../$(PYBIN)/mypy rjacq

lint-web:
	cd $(WEB_DIR) && pnpm lint && pnpm typecheck

format: ## Auto-format (ruff, prettier)
	cd $(API_DIR) && ../../$(PYBIN)/ruff check --fix rjacq tests
	cd $(API_DIR) && ../../$(PYBIN)/ruff format rjacq tests
	cd $(WEB_DIR) && pnpm format

e2e: ## Playwright end-to-end tests
	cd $(WEB_DIR) && pnpm exec playwright test

deploy-provision: ## Provision Azure prod infra (Container Apps) — see docs/DEPLOYMENT.md
	./scripts/provision-azure.sh

clean: ## Remove build artifacts and caches
	rm -rf $(VENV) $(WEB_DIR)/node_modules $(WEB_DIR)/dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

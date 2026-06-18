# RJourney Acquisitions Platform

Ingest RV-resort acquisition documents, normalize them to one schema, underwrite each acquisition,
benchmark it against a local competitive set, and track it through a phase-gated pipeline —
mobile-first, with an in-app feedback loop and built-in observability.

> **Source of truth:** `docs/rjourney-acquisitions-design-document-v0.2.md`.
> **How we build:** `CLAUDE.md`. **How to contribute:** `CONTRIBUTING.md`.

## Status

Greenfield. Build order (see design doc §11): **Phase 0 Foundation → 1 Ingestion & mapping →
2 Underwriting → 3 Comp intelligence → 4 Pipeline, gates & feedback.**

## Stack

FastAPI + PostgreSQL/pgvector + Redis (backend, workers) · React + Vite + Tailwind (frontend) ·
Anthropic Claude API + Voyage embeddings (AI) · S3-compatible object storage · Sentry +
structured logs (observability) · GitHub + `anthropics/claude-code-action@v1` (feedback dispatch).

## Repository layout

```
apps/api/     FastAPI app (domain modules + workers)
apps/web/     React + Vite SPA
migrations/   Alembic
docs/         design doc, ADRs
.github/      workflows, issue/PR templates
```

## Prerequisites

- Docker + Docker Compose
- Python 3.12 and `uv`
- Node 20+ and `pnpm`
- A `.env` file — copy `.env.example` and fill it in (see that file for each variable)

## Quick start

```bash
cp .env.example .env        # then fill in values
make bootstrap              # install deps + pre-commit hooks
make migrate                # apply database migrations
make dev                    # api + web + workers via docker-compose
```

- Web: http://localhost:5173
- API + OpenAPI docs: http://localhost:8000/docs

## Common commands

```bash
make test       # backend (pytest) + frontend (vitest)
make lint       # ruff, mypy, eslint, prettier --check
make format     # auto-format
make e2e        # Playwright end-to-end
make migration m="add feedback tables"
```

## Deployment

Production runs on **Azure Container Apps** with managed Postgres/Redis/object storage and an
automated, zero-downtime GitHub Actions pipeline (`.github/workflows/deploy.yml`). Full
provisioning, the fast update flow, and the data-safety / migration discipline are in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Feedback → fix loop

The app's floating **"?"** widget files feature/bug/question items into a triage queue. A
reviewed item is dispatched as a GitHub issue mentioning `@claude`; the GitHub Action opens a
PR for human review. See `CONTRIBUTING.md` and `.github/workflows/claude.yml`. Set up the
Action with `/install-github-app` from the Claude Code terminal, or follow the manual steps in
the design doc.

## Security

Secrets via env/secret store only. SHIELD access is read-only. RBAC enforced server-side.
Never commit `.env`. See `CLAUDE.md` for the full security rules.

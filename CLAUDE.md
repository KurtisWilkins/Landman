# CLAUDE.md

Operating rules for any Claude Code session (interactive or GitHub Action) working in this
repository. Keep this file the single, concise source of *how we build*; the **what** lives in
`docs/rjourney-acquisitions-design-document-v0.2.md` (the design doc).

> **Get up to speed first:** read @docs/PROJECT-CONTEXT.md — current state, the rjourney.com brand
> system, and the acquisition-by-acquisition promote waterfall (Partner Equity / RJourney Equity).
> Where it and the older design doc disagree, PROJECT-CONTEXT.md is the newer intent.

---

## What this is

RJourney Acquisitions Platform — a web app that ingests RV-resort acquisition documents,
normalizes them to one schema, underwrites acquisitions (5-yr levered cash flow, IRR, 3-hurdle
waterfall), scrapes a local competitive set, and tracks a phase-gated pipeline. It carries an
in-app feedback widget that dispatches fixes back through this same GitHub Action.

## Golden rules (read first)

1. **The design doc's §8 data model is the contract.** Conform to it. If a change needs a schema change, call it out explicitly in the PR and update the doc in the same PR.
2. **Never invent a `[DECISION]` value.** Anything the design doc marks `[DECISION]` is unresolved. Read it from config/env with a clearly-named placeholder and a `# TODO(decision): …` comment. Do not bake a guessed number (hurdle rates, splits, thresholds) into logic.
3. **Human-in-the-loop, always.** AI proposes; a person accepts. Never auto-merge, never auto-advance a acquisition phase, never auto-lock a pro forma or GL mapping.
4. **Provenance is sacred.** Every financial line keeps its original seller text, mapped account, confidence, and NOI placement. Every assumption keeps baseline + override + author + note. Don't drop or overwrite provenance to simplify.
5. **Secrets and PII.** Never commit secrets. Never log secrets, credentials, full financials, or raw feedback screenshots. SHIELD access is **read-only**.
6. **Small, reviewable PRs.** One concern per PR, linked to its issue. If a task balloons, stop and split it.

## Tech stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic. Package/deps via `uv`.
- **Frontend:** TypeScript (strict), React, Vite, Tailwind, TanStack Query, React Router, Recharts. Package manager `pnpm`.
- **Data:** PostgreSQL 16 + `pgvector`. Redis for the job queue (Arq).
- **AI:** Anthropic Claude API (extraction, classification, summaries); Voyage embeddings for GL mapping shortlist. `claude-sonnet-4-6` default; escalate to `opus` only for genuinely complex reasoning.
- **Infra:** Docker + docker-compose for local; object storage is S3-compatible.
- **Observability:** structured JSON logs, Sentry (front + back), Prometheus metrics.

## Repository layout

```
apps/
  api/        FastAPI app, domain modules, workers
  web/        React + Vite SPA
migrations/   Alembic
docs/         design doc, ADRs
.github/      workflows, issue/PR templates
docker-compose.yml
CLAUDE.md  README.md  CONTRIBUTING.md  .env.example
```

Backend is organized by domain, not by layer: `acquisitions/`, `ingestion/`, `mapping/`,
`underwriting/`, `comps/`, `gates/`, `feedback/`, `shield/`, plus shared `core/` (config,
logging, auth, db).

## Commands

Assume these exist (create/repair them if missing) and use them rather than ad-hoc calls:

```
make bootstrap     # install all deps (uv sync, pnpm install), set up pre-commit
make dev           # run api + web + workers locally via docker-compose
make migrate       # alembic upgrade head
make migration m="msg"   # autogenerate a revision
make test          # backend (pytest) + frontend (vitest)
make lint          # ruff, mypy, eslint, prettier --check
make format        # ruff format, prettier --write
make e2e           # Playwright
```

A PR must pass `make lint` and `make test` before it is opened.

## Coding standards

**Python**
- Type-hint everything; `mypy` clean. Pydantic models for all I/O boundaries.
- `ruff` is the linter and formatter; no manual style debates.
- FastAPI routers thin; business logic in service functions; DB access in repository functions. No raw SQL in routers.
- Use SQLAlchemy 2.0 style (`select()`), parameterized — never string-interpolate SQL.
- Money as integer cents or `Decimal`; never float for financial values.

**TypeScript / React**
- `strict` on; no `any` without a `// eslint-disable` justification.
- Server state via TanStack Query; local UI state via hooks. No global mutable singletons.
- Components are presentational where possible; data-fetching lives in hooks.
- Tailwind utility classes; use the brand tokens (`brand` navy, `accent` gold, `ink`, `paper`/`surface`, `figure` mono) defined in `apps/web/tailwind.config.ts` — the single theme source, extracted from rjourney.com. Mobile-first, then `md:`/`lg:`.
- **No browser storage** (`localStorage`/`sessionStorage`) for app state; use query cache + server.

**API design**
- Resource-oriented, matches the design doc §9 surface. Validate every input with Pydantic.
- Errors are structured JSON: `{ "error": { "code", "message", "detail" } }`. Never leak stack traces to clients.
- All money/rates returned in documented units; document them in the OpenAPI schema.

**Database / migrations**
- Every schema change is an Alembic migration, reviewed in the PR. Never edit a shipped migration; add a new one.
- Match §8 column names exactly. `raw_payload jsonb` retained on ingest-fed tables.
- `financial_lines.account_code` is nullable on purpose (unmapped lines persist).

**Production data safety (live data — handle with care)**
- Migrations are **additive by default**. An `upgrade()` must not drop a table/column/type or
  otherwise destroy data unless a human has confirmed a backup and the loss is intended — then
  mark the exact line `# allow-destructive: <reason>`. CI (`test_migration_safety.py`) fails on an
  unmarked destructive op in any `upgrade()`. `downgrade()` is exempt and is never run in prod.
- **Before running the migrate job in prod, snapshot first.** Take an on-demand backup of the
  Postgres flexible server (`az postgres flexible-server backup …`) and confirm PITR retention.
- **Never run `alembic downgrade` against prod.** Roll forward with a new migration instead.
- **Review every autogenerated migration** before applying — `--autogenerate` will emit column/
  table drops on a model change; keep only the intended, additive parts.
- Ingest/edit paths **append, never overwrite**: re-uploaded financials create a new (dated)
  `financial_period`; prior versions are retained, not mutated. Provenance is sacred.

**Logging & observability**
- Structured JSON logs only. Thread a request/correlation ID through every flow (HTTP, workers).
- Log ingest jobs, GL mapping decisions, scrape runs, SHIELD syncs, auth events — never their secret/PII payloads.
- Initialize Sentry on both ends, tagged with the release/build hash.

## Testing requirements

- New business logic ships with unit tests. Bug fixes ship with a regression test that fails before the fix.
- The underwriting math (IRR, waterfall tiers, NOI bridge) requires tests with worked examples — these are correctness-critical.
- Ingestion/mapping: test the granularity-degradation path (leaf vs. coarse vs. unmapped) and the NOI add-back exclusion.
- Don't mock away the thing under test. Prefer real Postgres (testcontainers) for repository tests.

## Security rules

- Secrets only via env/secret store; `.env` is git-ignored; keep `.env.example` current when adding a variable.
- RBAC enforced server-side on every endpoint; never trust the client for role.
- SHIELD credentials are least-privilege read-only; the app must never attempt a write to SHIELD.
- Feedback screenshots may contain acquisition financials: store in access-scoped object storage, never log their contents, follow the redaction policy once set (`[DECISION]` D-32).
- Validate and size-limit all uploads; treat seller files as untrusted.

## Git, commits, PRs

- **Conventional Commits**: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`.
- Branch names: `feat/…`, `fix/…`. One issue per branch where possible.
- Every PR: link the issue, fill the PR template, keep it focused, and explain *what changed and why*. Update docs/ADRs in the same PR when behavior or decisions change.
- **No auto-merge.** A human approves and merges. CI (`lint`, `test`) must be green.

## Domain glossary (use these terms exactly)

- **Phase / gate:** the five pipeline stages; a gate is the set of blocking questions a acquisition must clear to advance. Acquisitions cannot skip phases.
- **NOI bridge:** normalization that strips owner debt service, non-operating items, and add-backs to produce a comparable NOI.
- **Leaf / coarse / unmapped:** GL mapping confidence — exact account, rolled-up subgroup, or no confident match.
- **SHIELD:** RJourney's existing (read-only) operations database; source of baseline underwriting assumptions.
- **Hurdle / waterfall:** return thresholds (pass/fail) and the tiered LP/GP promote split.
- **Comp set:** competitors within a 50-mile radius of the target.

## What NOT to do

- Don't hard-code any `[DECISION]` value or business threshold.
- Don't bypass human review, auto-advance phases, or auto-lock mappings/pro formas.
- Don't add a dependency without noting it in the PR description and why.
- Don't loosen RBAC, log PII/secrets, or write to SHIELD.
- Don't mirror a seller's P&L structure into our schema — map into the RJourney chart (§8.5).
- Don't introduce browser storage in the frontend.

## Definition of done

Code + tests + passing `lint`/`test`, docs/ADR updated if behavior or a decision changed,
PR linked to its issue, provenance and `[DECISION]` rules honored, and a human has reviewed it.

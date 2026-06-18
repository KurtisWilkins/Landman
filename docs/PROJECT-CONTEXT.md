# PROJECT-CONTEXT.md — Landman / RJourney Acquisitions

> **Read this first.** Single source for getting a Claude session up to speed: *what this is,
> where it lives, the active direction, and what's true today vs. what we still want.*
> The **how-we-build rulebook is [`CLAUDE.md`](../CLAUDE.md)**; the **what-it-does spec is the
> design doc** ([`docs/rjourney-acquisitions-design-document-v0.2.md`](rjourney-acquisitions-design-document-v0.2.md)).
> Where this file and the older design doc disagree, this file is current — see
> "Shipped vs. the older design doc" for what still needs reconciling.

## What this project is

A web app for RJourney's **RV-resort acquisitions**: ingest seller documents, normalize them to
one schema, underwrite each deal (5-yr levered cash flow, IRR, equity multiple, promote
waterfall), benchmark against a local competitive set, and track deals through a phase-gated
pipeline. An in-app **"?" feedback widget** files items that dispatch back through a GitHub Action.

- **Names:** GitHub repo is **`Landman`**; the product / internal codename is **"RJourney
  Acquisitions Platform"**; the Python package is **`rjacq`**. All three refer to the same thing.
- **Repo:** https://github.com/KurtisWilkins/Landman (GitHub — *not* Azure DevOps).
- **Local clone:** `C:\Users\kuwil\OneDrive\Documents\AutomationProjects\Landman`

## Hosting / infra

- **Production: Azure Container Apps** with managed Postgres/Redis and Azure Blob (S3-compatible
  via s3proxy) object storage. "Azure" = where it's *deployed*; the source of truth is the
  GitHub repo above.
- **Deploy:** automated, zero-downtime GitHub Actions pipeline — [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml).
- **Provision:** [`scripts/provision-azure.sh`](../scripts/provision-azure.sh) (Cloud Shell ready; builds images with `az acr build`). Runbook: [`docs/DEPLOYMENT.md`](DEPLOYMENT.md).

## Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic. Deps via `uv`.
  Postgres 16 + `pgvector`; Redis + Arq job queue.
- **Frontend:** TypeScript (strict), React, Vite, Tailwind, TanStack Query, React Router,
  Recharts. Package manager `pnpm`. **No browser storage** for app state.
- **AI:** Anthropic Claude API (extraction/classification/summaries) + Voyage embeddings (GL
  mapping shortlist). Default `claude-sonnet-4-6`; escalate to Opus only for hard reasoning.

## Run locally

```bash
cp .env.example .env     # then fill in values
make bootstrap           # uv sync + pnpm install + pre-commit
make migrate             # alembic upgrade head
make dev                 # api + web + workers via docker-compose
# Web → http://localhost:5173   API + OpenAPI → http://localhost:8000/docs
make test | make lint | make format | make e2e | make migration m="msg"
```

## Where things live

```
apps/api/rjacq/   FastAPI app, organized by domain (not by layer):
    deals/ ingestion/ mapping/ underwriting/ comps/ gates/ feedback/ shield/
    population/ models/ schemas/ seeds/ + shared core/ (config, db, auth, logging)
    underwriting/engine.py   ← pure, tested promote/IRR/waterfall math (the engine)
apps/web/src/     React SPA:
    components/AppShell.tsx   ← nav + branding (currently plain "RJourney" text, no logo)
    routes/Pipeline.tsx       ← pipeline overview (phase buckets + deal list)
    routes/DealDetail.tsx + routes/deal/*Tab.tsx  ← deal workspace (Proforma/Comps/Gates/Market/GLDocs)
    api/                      ← generated contract types + TanStack Query hooks
    index.css, tailwind.config.ts  ← theme tokens (see design target below)
migrations/  docs/  .github/
```

## Design target — match rjourney.com  ✅ shipped

The app matches the **RJourney brand** at https://rjourney.com — tokens extracted from the live
site's Breakdance `global-settings.css` and centralized in **one theme source**
(`apps/web/tailwind.config.ts`; base layer in `index.css`). Do not hardcode hex across components.
- Brand **navy `#25314B`** (primary actions / headings / links), **gold accent `#FEBB20`**, body
  ink `#252525`, warm paper `#FCFBFA`, white surfaces. **Gabarito** is the brand typeface;
  figures stay monospaced (`figure`). 3px control radius; ×1.25 modular type scale.
- Logo assets live in `apps/web/public/` (`rjourney-blue.png`, `rjourney-white.png`).
- Earlier history: the first cut used placeholder *forest/bone/brass* wireframe tokens — that's
  the "doesn't look like rjourney.com" complaint that prompted this work. It was replaced by the
  brand theme in `style(web): apply RJourney brand theme` (PR #26). The only remaining
  forest/bone/brass references are in **docs** (the design doc §6 — see gaps below), not in code.

## Core feature — deal-by-deal promote waterfall  ✅ engine shipped

A **reusable engine**, not a one-off page — implemented as a pure, UI/DB-free module so the math
is unit-tested against the spreadsheet's worked example. Each deal feeds the same structure with
its own inputs and is computed **independently (deal-by-deal)**.
- Engine: `apps/api/rjacq/underwriting/promote.py` (`run_promote_waterfall(PromoteInputs)`)
- API: `apps/api/rjacq/api/promote.py` · schemas `schemas/promote.py`
- UI: `apps/web/src/routes/Promote.tsx`
- Tests / regression: `apps/api/tests/test_promote.py`, `tests/test_promote_api.py`

**Engine logic** — reconstructs the **promote spreadsheet, sheet "Waterfall Template"** (the
worked example is pinned in `test_promote.py`; the source `.xlsx` itself is not committed):
- Per-deal inputs: start date, total equity, asset LTV, RJourney co-invest % (Partner % =
  1 − co-invest), four IRR hurdles (**8 / 15 / 20 / 20 %**), four promote splits
  (**10 / 20 / 30 / 30 %**), return-case assumptions (yr-1 yield, growth, bespoke exit
  reversion), optional acquisition & management fees. Dates are annual (EOMONTH +12); returns are
  date-based **XIRR** (actual/365), matching the sheet.
- Flow: generate deal-level cash flows → return capital first → four sequential IRR-hurdle tiers
  → split residual.
- **Promote tier-shift rule:** a hurdle's promote % applies to cash *above* it — 100% to equity
  up to 8%, then 90/10 (8→15%), 80/20 (15→20%), 70/30 above.
- Outputs: combined investor cash flows split into **Partner Equity** (net of promote paid to
  RJourney) and **RJourney Equity** (co-invest pari passu + 100% of carry/fees), plus Deal-Level
  (no promote) for reference; reconciliation flag `cashflow_ties_out`.
- **Regression (default scenario, asserted in `test_promote.py`):** Deal-Level **18.6% / 2.23x**;
  Partner **17.5% / 2.13x**; RJourney **27.6% / 3.19x**.

**Views status:** the engine + API + a `Promote` route exist. Wiring the pipeline-overview
columns (per-deal Partner/RJourney/Deal-Level IRR & MOIC) and fully live editable deal-detail
inputs is the remaining product surface to confirm — check `routes/Pipeline.tsx` and
`routes/Promote.tsx` against the "Views" intent before assuming it's all wired.

## Naming rules (strict)

Genericized labels only — no fund/JV/brand names in the promote structure:
- "Fund 21" / "LP" → **Partner Equity** (or "Partner")
- "GP" → **RJourney Equity** (or "RJourney")
- Deal name = the property name; no "JV 1" style labels.

## Shipped vs. the older design doc (remaining reconciliation)

The brand theme and the promote waterfall (both described above) have **shipped** (PRs #26/#27).
What's left is making the older **design doc** match the code, plus a couple of cleanups:

1. **Design doc §6 (theme)** still describes forest/bone/brass tokens — update it to the shipped
   rjourney.com brand system (navy/gold/Gabarito). Per `CLAUDE.md` golden rule #1, the design doc
   is the contract, so this should be brought current.
2. **Design doc §5.7 / §8 (waterfall)** still describe a **3-hurdle, LP/GP** model
   (`waterfall_tiers.lp_split`/`gp_split`, breakpoints 8%/13%) and `[DECISION] A-2`. The shipped
   engine is **4-hurdle (8/15/20/20), Partner/RJourney, return-of-capital first, tier-shift**.
   Reconcile §8 (and note whether the `waterfall_tiers` schema is still used).
3. **Two waterfall modules coexist:** the older generic `underwriting/engine.py` (3-hurdle LP/GP
   European, terminal-distribution) and the new `underwriting/promote.py` (the deal-by-deal
   Partner/RJourney engine). Confirm which is canonical for the product and whether `engine.py`
   should be retired or kept for its NOI-bridge / pro-forma helpers.

## Conventions & working style

- **Plan before execute:** explore, propose a plan with tradeoffs flagged, **wait for approval
  before writing code.** Small, reviewable, single-concern PRs; no auto-merge.
- Keep the waterfall math a **pure, unit-tested module** decoupled from the UI and data layer
  (it already is — `underwriting/engine.py` decides no business values; thresholds/splits are
  passed in). Worked-example tests are correctness-critical.
- Theme changes are **presentational only** — never alter calculation/business logic to style.
- Money as integer cents or `Decimal`, never float. Don't hard-code any `[DECISION]` value.

## Current status

- **Done / merged (Phases 0–3 + recent):** repo scaffold; domain backend (ingestion, GL mapping,
  underwriting, comps, gates, feedback, SHIELD connector, population rings via US Census ACS);
  React app shell + deal workspace (Proforma/Comps/Gates/Market tabs) + feedback widget; Azure
  Container Apps provisioning + deploy pipeline; **rjourney.com brand theme** (PR #26); **deal-by-
  deal promote waterfall** engine + API + UI + tests (Partner/RJourney, 4-hurdle); new-deal form,
  O/M extraction, financial-period versioning, admin-managed integration keys, EasyAuth edge auth.
- **Partially wired:** some screens render against the generated contract but fall back to "lands
  with backend" messaging when an endpoint isn't live yet. GL Mapping queue is still a
  `Placeholder`. Verify the promote views (pipeline columns + live deal-detail editing) are fully
  wired before assuming so.
- **Next up:** (1) bring the **design doc current** (§6 theme, §5.7/§8 waterfall) — see
  reconciliation above; (2) decide the fate of the older `underwriting/engine.py` vs the new
  `promote.py`; (3) commit (or formally reference) the source "Waterfall Template" spreadsheet.

## Reference docs

- Design doc (the **what**): [`docs/rjourney-acquisitions-design-document-v0.2.md`](rjourney-acquisitions-design-document-v0.2.md)
- Build rulebook (the **how**): [`CLAUDE.md`](../CLAUDE.md) · contributing: [`CONTRIBUTING.md`](../CONTRIBUTING.md)
- Deployment runbook: [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) · kickoff: [`docs/BUILD-KICKOFF.md`](BUILD-KICKOFF.md)
- ADRs: [`docs/adr/`](adr/)

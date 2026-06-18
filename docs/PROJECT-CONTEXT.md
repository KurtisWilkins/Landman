# PROJECT-CONTEXT.md — Landman / RJourney Acquisitions

> **Read this first.** Single source for getting a Claude session up to speed: *what this is,
> where it lives, the active direction, and what's true today vs. what we still want.*
> The **how-we-build rulebook is [`CLAUDE.md`](../CLAUDE.md)**; the **what-it-does spec is the
> design doc** ([`docs/rjourney-acquisitions-design-document-v0.2.md`](rjourney-acquisitions-design-document-v0.2.md)).
> Where this file and those disagree, this file describes the **newer intent** — see
> "New direction vs. current repo" and treat those as open work, not as already-shipped.

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

## Design target — match rjourney.com

The app should visually match the **RJourney brand** at https://rjourney.com.
- Warm outdoor/RV brand; tagline **"Modern Comfort. Timeless Adventure."**
- Brand **blue** primary. White wordmark on dark/photo backgrounds, blue/dark wordmark on light.
- Logos: white `https://rjourney.com/wp-content/uploads/RJourneylogoWhiteBLD2.png`;
  blue `https://rjourney.com/wp-content/uploads/RJourneylogoBlueBLD2.png`.
- Extract brand fonts + exact palette from the live site's CSS and centralize them as tokens in
  **one theme source** (`apps/web/tailwind.config.ts` + `index.css`). Do not hardcode hex across
  components.
- **Known gap (this is why it "doesn't look like rjourney.com at all"):** the current theme is a
  *forest-green / bone-cream / brass* palette with placeholder hex values taken from an internal
  wireframe (`tailwind.config.ts:11-13`, `TODO(stream-D)`), there is **no logo, no brand fonts,
  and no blue**, and `index.css` carries no brand styling. The rebrand to rjourney.com has **not
  been done yet.**

## Core feature — deal-by-deal promote waterfall

A **reusable engine**, not a one-off page. Each pipeline property feeds the same structure with
its own inputs and is computed **independently (deal-by-deal)**.

**Views**
- *Pipeline overview:* all deals with per-deal Partner Equity / RJourney Equity / Deal-Level IRR
  & MOIC, equity contributed, promote value.
- *Deal detail:* the full waterfall populated by the selected deal, every input editable,
  recalculating live; edits persist to that deal.

**Engine logic** — source of truth: the **promote spreadsheet, sheet "Waterfall Template"**
(⚠️ not in the repo yet — add it under `docs/` or reference it, and verify the numbers below):
- Per-deal inputs: start date, total equity, asset LTV, RJourney co-invest % (Partner % =
  1 − co-invest), four IRR hurdles (**8 / 15 / 20 / 20 %**), four promote splits
  (**10 / 20 / 30 / 30 %**), return-case cash-flow assumptions (yr-1 yield, growth, exit),
  optional acquisition & management fees.
- Flow: generate deal-level cash flows → return capital first → four sequential IRR-hurdle tiers
  → split residual.
- **Promote tier-shift rule:** a hurdle's promote % applies to cash *above* it — 100% to equity
  up to 8%, then 90/10 (8→15%), 80/20 (15→20%), 70/30 above.
- Outputs: combined investor cash flows split into **Partner Equity** (net of promote paid to
  RJourney) and **RJourney Equity** (co-invest pari passu + 100% of carry/fees), plus Deal-Level
  (no promote) for reference.
- **Regression check (expected defaults):** Deal-Level **18.6% / 2.23x**; Partner
  **17.5% / 2.13x**; RJourney **27.6% / 3.19x**.

## Naming rules (strict)

Genericized labels only — no fund/JV/brand names in the promote structure:
- "Fund 21" / "LP" → **Partner Equity** (or "Partner")
- "GP" → **RJourney Equity** (or "RJourney")
- Deal name = the property name; no "JV 1" style labels.

## New direction vs. current repo (the gaps to close)

The repo predates the decisions above. Concretely:

1. **Theme:** current = forest/bone/brass placeholders, no logo/fonts/blue → **rebrand to
   rjourney.com.** Presentational only; never change calc logic to apply a style.
2. **Waterfall engine:** current `underwriting/engine.py` is a **3-hurdle, LP/GP, European
   terminal-distribution** waterfall (breakpoints 8%/13%, splits 100/0, 80/20, 70/30 — design
   doc §5.7 / §8, with `waterfall_tiers.lp_split`/`gp_split`). New spec = **4-hurdle
   (8/15/20/20), Partner/RJourney, return-of-capital first, tier-shift promote.** This is a
   re-spec, not a tweak — it resolves design-doc `[DECISION] A-2` with new values.
3. **Naming:** sweep LP/GP (and any "Fund 21") → **Partner Equity / RJourney Equity** across
   schema, API, and UI. ⚠️ Per `CLAUDE.md` golden rule #1 the **design doc §8 data model is the
   contract** — update §8 (and the Alembic migration) in the **same PR** as any rename.

## Conventions & working style

- **Plan before execute:** explore, propose a plan with tradeoffs flagged, **wait for approval
  before writing code.** Small, reviewable, single-concern PRs; no auto-merge.
- Keep the waterfall math a **pure, unit-tested module** decoupled from the UI and data layer
  (it already is — `underwriting/engine.py` decides no business values; thresholds/splits are
  passed in). Worked-example tests are correctness-critical.
- Theme changes are **presentational only** — never alter calculation/business logic to style.
- Money as integer cents or `Decimal`, never float. Don't hard-code any `[DECISION]` value.

## Current status

- **Done / merged (Phases 0–3):** repo scaffold, domain backend modules (ingestion, GL mapping,
  underwriting engine, comps, gates, feedback, SHIELD connector, population rings via US Census
  ACS), React app shell + deal workspace (Proforma/Comps/Gates/Market tabs), feedback widget,
  and the Azure Container Apps provisioning + deploy pipeline.
- **Partially wired:** several screens render against the generated contract but fall back to
  "lands with backend" messaging when the endpoint isn't live yet (e.g. Pipeline `/deals`,
  Proforma). GL Mapping queue is still a `Placeholder`.
- **Broken / next up:** (1) **rebrand to rjourney.com** (the visible complaint); (2) **re-spec
  the promote waterfall** to the 4-hurdle Partner/RJourney model above; (3) **naming sweep**
  LP/GP → Partner/RJourney (+ design-doc §8 + migration); (4) add the promote spreadsheet
  ("Waterfall Template") to the repo and pin the regression numbers as tests.

## Reference docs

- Design doc (the **what**): [`docs/rjourney-acquisitions-design-document-v0.2.md`](rjourney-acquisitions-design-document-v0.2.md)
- Build rulebook (the **how**): [`CLAUDE.md`](../CLAUDE.md) · contributing: [`CONTRIBUTING.md`](../CONTRIBUTING.md)
- Deployment runbook: [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) · kickoff: [`docs/BUILD-KICKOFF.md`](BUILD-KICKOFF.md)
- ADRs: [`docs/adr/`](adr/)

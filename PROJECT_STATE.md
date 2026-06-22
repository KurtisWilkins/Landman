# Project state

Snapshot of where the RJourney Acquisitions Platform stands. For the full contract see
`docs/rjourney-acquisitions-design-document-v0.2.md` (§8 data model, §9 API); for onboarding see
`docs/PROJECT-CONTEXT.md`; for the decision log see `DECISIONS.md`; for the task list see `TASKS.md`.

_Last updated: 2026-06-22._

## What it is

Monorepo: `apps/api` (FastAPI / Python 3.12 / SQLAlchemy 2.0 async / Alembic) + `apps/web`
(React / TS / Vite / Tailwind / TanStack Query). Package: `rjacq`. Deployed to Azure Container Apps;
live at https://landman.rjourney.com. Each deal is an **acquisition** (never "project").

## Underwriting flow — single source of truth (complete)

The per-acquisition data flow is wired end-to-end against **one canonical store**, fully reactive,
with persistence everywhere:

```
upload OM / P&L → editable NOI → canonical store → pro forma → 60-month cash flow → promote
```

- **Canonical store = `proforma_inputs`** (per-acquisition assumptions) **+ `waterfall_tiers`**
  (promote hurdles/promotes). Purchase price lives on `acquisitions` and is read through. The
  pro forma, the 60-month grid, and the promote waterfall all **read** from the store; none keeps
  its own copy. See `DECISIONS.md` D-1.
- **Reactivity is cached-derived** (D-2): a write to any shared assumption — pro-forma inputs, the
  price (`PATCH /acquisitions`), or the waterfall tiers — runs one recompute and persists the
  results (`proforma_results`, `proforma_summary`, `proforma_monthly`); GETs serve the cache.
- **Pro forma** (`underwriting/proforma.py`, pure + unit-tested): sizes amortizing debt with an
  optional IO period (honoring a `loan_amount` override), projects NOI on the GL structure with
  per-line growth, and assembles the levered equity stream.
- **60-month cash flow** (`build_monthly_cashflows`): each year's revenue/opex/CapEx spread evenly
  across 12 months (no fabricated seasonality) + the real monthly debt service; each 12-month block
  rolls up to the annual pro forma (regression-tested). Exposed at `GET /proforma-monthly`.
- **Promote** (`underwriting/promote.py`, pure): consumes the annual rollup via `cashflow_override`
  and the persisted promote terms (co-invest, fees, start date, hurdles/promotes). Custom terms set
  in the UI persist and drive the headline returns shown in the acquisition header + pipeline.

### Key endpoints
`GET/PUT /acquisitions/{id}/proforma-inputs` · `GET /acquisitions/{id}/proforma` ·
`GET /acquisitions/{id}/proforma-monthly` · `GET /acquisitions/{id}/returns` ·
`GET/PUT /acquisitions/{id}/waterfall-tiers` · `PATCH /acquisitions/{id}` (price → recompute) ·
`GET/PUT /underwriting-defaults` (admin seed defaults).

## Underwriting page — GL mapping → budget → defaults (complete)

The acquisition Underwriting page produces the **stabilized NOI** that feeds the flow above. End to
end: **upload P&L → GL map (confirm) → prior-year-vs-year-one budget → review + lock → stabilized
NOI**. See `DECISIONS.md` D-8…D-11.

- **GL mapping** (`mapping/`, `GLDocsTab`): the existing learned → embed+classify → never-drop
  engine runs in a **background Arq worker** after upload; the confirm workstation buckets lines
  (needs review / auto-mapped / confirmed) with a GL-chart picker, NOI selector, learn toggle,
  **remap / split** (one line → many GLs via `financial_lines.split_parent_id`), and bulk confirm.
  Learned mappings are **per seller** so re-uploads resolve without the LLM. First-time AI
  suggestions await §14 C-20 (Voyage/Claude providers); until then it does learned + manual.
- **Budget** (`underwriting/budget*.py`, `BudgetTab`): each canonical GL's prior-year actuals
  (computed on read from `raw_payload`) beside the editable year-one cells (stored in
  `budget_lines`), with $/% variance and a provenance badge (actuals / default / to review /
  edited). Collapsed annual; expand for the month-by-month view.
- **Defaults engine** (`underwriting/budget_defaults.py`, pure): Shield (fixed, overrides),
  marketing (two lines), PPC (two-line formula). Rates + target GL codes are config; **no-op until
  configured** so nothing is guessed.
- **Lock + flow-through**: `effective_stabilized` precedence = manual override → **locked budget
  rollup** → NOI bridge; lock gated on zero placeholders + unmapped; lock/unlock recompute.

### Budget endpoints
`GET/PUT /gl-accounts` (chart picker) · `POST /acquisitions/{id}/mapping/confirm|split` ·
`GET /acquisitions/{id}/budget` · `PATCH …/budget` (cell edit) · `POST …/budget/seed|lock|unlock`.

## Shipped

**Single source of truth (PRs #41–#46):**
1. **#41** — canonical store schema (additive `proforma_inputs` / `underwriting_defaults` columns).
2. **#42** — pro forma + promote read from the store (loan_amount, split growth, persisted terms).
3. **#43** — price edit triggers the recompute (closed the "editing price doesn't resize debt" bug).
4. **#44** — 60-month monthly cash-flow engine + `proforma_monthly` table + endpoint.
5. **#45** — ProformaTab UI: new fields + the 60-month grid.
6. **#46** — promote persistence: `waterfall-tiers` endpoints + PromoteTab load/save.

**Underwriting page (PRs #48–#54):**
7. **#48** — auto-map runs in a background worker + seller-scoped learned mappings.
8. **#49** — GL mapping confirm workstation + `GET /gl-accounts`.
9. **#50** — split one seller line across GLs (`split_parent_id`).
10. **#51 / #52** — budget model + grid (prior-year beside editable year-one).
11. **#53** — budget lock + flow-through to stabilized NOI.
12. **#54** — budget defaults engine (Shield / marketing / PPC).

## Pending

- **Deploy**: the SSOT release (`b2c3d4e5f6a7` + `c3d4e5f6a7b8`) is live (SHA `8bb2b59`). The next
  deploy applies the Underwriting-page migrations `d4e5f6a7b8c9` (split-parent) + `e5f6a7b8c9d0`
  (budget tables) — both additive; back up Postgres first per CLAUDE.md.
- **Activate the defaults engine**: set the five `*_account_code` + `ppc_rate` / `ppc_target_volume`
  / `ppc_intercompany_pct` config (needs the full GL chart, §14 B-13). Until then the budget seeds
  from actuals only.
- Known future enhancements are tracked in `TASKS.md` (monthly-direct promote, P&L-parsing UX
  guards, first-time AI mapping suggestions = §14 C-20, etc.).

## Local toolchain notes

Python 3.12 + uv + the repo `.venv`; Node 24 (pnpm not on PATH — run generators via
`node node_modules/<tool>/bin/...`). Regenerate the contract after backend changes:
`python -m rjacq.openapi apps/web/openapi.json` (set `PYTHONIOENCODING=utf-8` on Windows) then
`openapi-typescript ./openapi.json -o ./src/api/types.ts`. CI is the source of truth for pytest
(needs Postgres) and LF formatting.

# Decisions

A running log of design/architecture decisions for the RJourney Acquisitions Platform that
aren't already captured in `docs/adr/` (those remain the home for the larger infra/provider ADRs)
or the canonical contract in `docs/rjourney-acquisitions-design-document-v0.2.md` (§8/§9).

Newest first.

---

## 2026-06-22 — Underwriting single source of truth (Parts 1–6, PRs #41–#46)

The per-acquisition data flow **upload → editable NOI → pro forma → 60-month cash flow → promote**
was wired end-to-end against one canonical store. The decisions below were taken with the user.

### D-1 — Canonical store schema: extend `proforma_inputs` in place

**Decision.** `proforma_inputs` is the single source of truth for per-acquisition assumptions.
Extended it in place with additive, nullable columns rather than introducing a new
`deal_assumptions` table.

- **Reused** the existing `waterfall_tiers` table for the promote hurdles/promotes (no new table).
- **Price stays on `acquisitions`** (`purchase_price ?? ask_price`, read through `_purchase_price()`)
  — never copied into the store (one authoritative owner per number).
- `underwriting_defaults` (+ the `BUILT_IN` dict) remains the **seed** layer (pre-fills a new
  acquisition's inputs); `proforma_results` / `proforma_summary` / `proforma_monthly` are **derived
  output caches** (recomputed on write, never user-edited).
- **Equity stays derived** (`price − loan`); there is no independent editable equity column (avoids
  an over-determined price/loan/equity triangle).

**Why.** `proforma_inputs` was already PK = `acquisition_id` (1:1) and already the recompute trigger.
Widening it is a purely additive, zero-backfill migration: every new column is nullable and falls
back to today's behavior, so every pre-existing acquisition computes identically until a value is
set. A new aggregate table would have meant a data-copy migration + a guarded destructive drop on
live data for no functional gain.

New columns (migration `b2c3d4e5f6a7`): `loan_amount`, `revenue_growth`, `expense_growth`,
`rjourney_coinvest_pct`, `acquisition_fee_pct`, `mgmt_fee_pct`, `start_date` on `proforma_inputs`;
the three JV-term seeds on `underwriting_defaults`.

### D-2 — Reactivity: cached-derived (recompute on write)

**Decision.** Any write to a shared assumption (pro-forma inputs, the `acquisitions` price, or the
waterfall tiers) runs the full recompute once in the service layer and persists the results; all
reads serve the cache. GET endpoints never invoke an engine.

**Why.** The pipeline list computes returns per row, so recompute-on-read would make it
`O(deals × full waterfall)` (plus the monthly XIRR bisection cost) on every page render. This
extends the already-working materialize-on-write design (`proforma_results`/`summary`).

**Consequence (closed in PR #43).** The `PATCH /acquisitions` price edit now routes through the same
recompute path — previously editing the price did **not** re-size debt, which made the
single-source-of-truth claim false.

### D-3 — Waterfall granularity: monthly grid, annual rollup into the (unchanged) waterfall

**Decision.** Build a 60-month monthly cash-flow grid for display/export and correct monthly debt
timing, but feed the promote waterfall an **annual rollup** (which is exactly the annual pro forma
it already consumes). The validated, spreadsheet-tied promote math (daily-accrual tiers, XIRR,
worked-example tests) is left **unchanged**.

**Why.** Lowest risk on the most load-bearing, hardest-to-verify code. A regression test asserts
the 12-month blocks roll up to the annual pro forma (debt service exact; the rest within Decimal
tolerance), so the rollup is provably consistent.

**Deferred.** Running the waterfall monthly-direct (true intra-year distribution timing) is a later
phase, once the monthly engine is proven.

### Supporting decisions

- **D-4 — `loan_amount` precedence.** A dollar `loan_amount` override wins over LTV when sizing debt;
  it's expressed as an effective LTV (`loan / price`) so the pure `size_debt` engine is unchanged.
  LTV becomes display-derived. Leverage readiness accepts an LTV **or** a `loan_amount`.
- **D-5 — Per-line growth.** `revenue_growth` / `expense_growth` escalate the revenue/opex lines
  independently; `NULL` falls back to the blended `noi_growth`.
- **D-6 — Promote-term defaults from config, not the DB.** Hurdle/promote default tuples
  (`[.08,.15,.20,.20]` / `[.10,.20,.30,.30]`) and the co-invest default (`0.10`) come from the
  promote engine's own defaults (the sanctioned config layer), never DB column server-defaults
  (CLAUDE.md rule #2). An acquisition that never customizes its promote is byte-identical to the
  standard waterfall.
- **D-7 — Grid horizon = full hold.** The monthly grid spans `hold_years × 12` months (= 60 for the
  default 5-year hold) rather than a hard 60-month cap, so the rollup-equals-annual invariant holds
  for any hold length.

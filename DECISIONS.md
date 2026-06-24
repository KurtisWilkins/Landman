# Decisions

A running log of design/architecture decisions for the RJourney Acquisitions Platform that
aren't already captured in `docs/adr/` (those remain the home for the larger infra/provider ADRs)
or the canonical contract in `docs/rjourney-acquisitions-design-document-v0.2.md` (§8/§9).

Newest first.

---

## 2026-06-24 — Two-column GL grid + deal archive (PRs #62, #63)

### D-12 — Underwriting grid: two editable columns, annual, add/remove line items

**Decision.** The Budget tab is a two-column annual grid — prior-year beside year-one — and **both
columns are editable** (correct an upload error or move an expense), not a read-only prior.

- **Prior stays provenance-aware**: prior defaults to the mapped P&L actual (badge `actuals`); an
  edit stores a `prior_amount` override (badge `edited`) but the uploaded value is still derivable
  from `FinancialLine.raw_payload`, so history isn't destroyed. Year-one defaults to prior.
- **Annual, not monthly**: the grid (and `budget_lines`) is now one row per line. Nothing downstream
  consumed budget-monthly (the 60-month cash flow comes from the pro-forma engine), so the
  month-by-month drill-down was folded away; it can return later. A guarded migration
  (`f3a4b5c6d7e8`) collapses any pre-existing per-month rows to annual.
- **TurboTax add/remove**: `+ Add line item` per section inserts a canonical GL **or** a custom
  free-text line. Custom lines have `account_code = NULL` + a `custom_label` + `section`, and are
  **`flagged_for_promotion`** to add to the GL chart later. The × **removes**: a custom line is
  hard-deleted; a GL/actuals line is `removed` from the year-one projection but **keeps its prior as
  reference** (drops from the year-one total only). Remove confirms when the row has data.
- **NOI roll-up is a pure, unit-tested function** (`budget.roll_up`): TOTAL REVENUE / TOTAL EXPENSES
  → NOI for both columns, above-the-line only — it reconciles with the downstream stabilized NOI
  bridge by construction. New API: `POST` / `PATCH /budget/line` + `DELETE /budget/line/{id}`.

### D-13 — Deal archive: soft-delete via an `archived_at` flag, never hard-delete

**Decision.** Archiving is a **separate `archived_at` timestamp** on `acquisitions`, orthogonal to
`status` — not a new `ARCHIVED` status value. There is **no hard-delete** anywhere in the UI.

- **Why the flag, not the enum:** archiving is independent of deal status (a deal can be
  active-but-archived); a flag preserves the real status, makes restore trivial (clear the flag),
  and is the canonical soft-delete. Migration `a7b8c9d0e1f2` (additive / nullable).
- The pipeline list **excludes archived** by default (`archived_at IS NULL`);
  `GET /acquisitions?archived=true` is the archived view. `POST …/archive` sets the flag +
  `archived_by`; `POST …/restore` clears it (status untouched). Both idempotent, gated on
  `ACQUISITION_WRITE`.
- UI: a ⋯ menu on each pipeline row (Archive, with confirm) + an "Archived" toggle that lists the
  archived deals with Restore.

---

## 2026-06-22 — Underwriting page: GL mapping + budget + defaults (PRs #48–#54)

Built the acquisition Underwriting page: upload → GL mapping → prior-year-vs-year-one budget →
defaults → review/lock → flow-through to the stabilized NOI (which feeds the engines above).

### D-8 — GL mapping: auto-map-with-confirm (keep + extend the existing engine)

**Decision.** Keep `propose_for_line` (learned → embed+classify → never-drop-unmapped) with the
mandatory human `confirm()` gate; do **not** go fully manual.

- **Wired `source_seller`** (was passed `None`): confirmed phrases are learned **per seller**, with a
  global fallback on miss — this is the "faster re-uploads" mechanism. Found the engine had **no
  caller**; it now runs in a **background Arq worker** after upload (chosen over inline — ~1 embed +
  1 classify per line, so a 200-line P&L shouldn't block the request) and degrades gracefully.
- **First-time AI suggestions** stay gated on §14 C-20 (Voyage + Claude providers are still stubs);
  until then the worker does learned reuse and the confirm workstation is the manual+learned surface.
- **SPLIT** (PR #50, migration `d4e5f6a7b8c9`): one nullable self-FK `financial_lines.split_parent_id`
  + a pure `allocate_split` (parts must sum to the parent). The parent becomes a non-counted
  container (`account_code = NULL`, already skipped by the NOI bridge); one confirmed child line per
  part. **MERGE** needs no new capability — confirm several lines to the same `account_code`.

### D-9 — Budget: prefill year-one from prior-year actuals; prior-year is computed on read

**Decision.** Year-one prefills from the mapped prior-year actuals (tagged `actuals`, overridable);
defaults fill the gaps; placeholders the rest. Not blank-start.

- **Prior-year monthly already lives in `FinancialLine.raw_payload`** (the QuickBooks recap parser
  stores each month) — so prior-year is **computed on read**, no prior-year table. Only the editable
  year-one cells are stored: new `budgets` + `budget_lines` (migration `e5f6a7b8c9d0`), one cell per
  `(acquisition, account, calendar month)` carrying provenance (`source`, `is_overridden`, note).
- **Line-item provenance is first-class** (`actuals` / `default` / `placeholder` / `edited`), visible
  on every row. Month alignment is by calendar month so "this June" sits beside "last June".

### D-10 — Defaults engine: formulas in code, numbers in config

**Decision.** A pure `budget_defaults.py` emits default lines; the **rates and the target GL account
codes are config** (CLAUDE.md rule #2), never literals in logic.

- **Shield** — fixed $1,000/mo, **overrides** any historical Shield line. **Marketing** — website
  $825 + secondary $850 as **two independent** lines. **PPC** — linear **two lines**:
  `google = site_count × target_volume × rate`; `intercompany = google × pct` (the self-charge stays
  visible with its own GL). `site_count` is read from the canonical `Acquisition`.
- The Shield/marketing amounts are the **confirmed** values; the **PPC rate/volume/% and all five
  target account codes default to `None`**, so the engine **no-ops until configured** (the full GL
  chart is §14 B-13) rather than guessing. Each default line is badged and per-deal overridable.
- **Open**: the exact GL account codes + the PPC `target_volume` unit / rate / intercompany-placement
  are still needed from the user to switch the defaults on.

### D-11 — Lock + flow-through: locked budget feeds stabilized NOI

**Decision.** `effective_stabilized` precedence is **manual override → locked-budget rollup → NOI
bridge**. No-op until a budget is locked (existing acquisitions unchanged).

- The locked budget rolls up through the **same `normalized_noi` machinery** the NOI bridge uses, so
  the two stabilized paths reconcile by construction. **Live-read** (not snapshot): editing a locked
  budget invalidates the lock and forces a re-lock.
- **Lock is gated** on zero placeholders **and** zero unmapped lines; lock/unlock recompute the pro
  forma. Recompute happens on lock/save, not per keystroke (per D-2).

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

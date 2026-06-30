# Decisions

A running log of design/architecture decisions for the RJourney Acquisitions Platform that
aren't already captured in `docs/adr/` (those remain the home for the larger infra/provider ADRs)
or the canonical contract in `docs/rjourney-acquisitions-design-document-v0.2.md` (§8/§9).

Newest first.

---

## 2026-06-30 — Canonical GL chart from the consolidated income statement; collapsible Budget tab

**Context.** We derived the canonical chart of accounts from RJourney's consolidated RV-portfolio
income statement (31 sheets: 4 consolidated views + 27 per-park). The hierarchy is not stored as
Excel row-grouping; it was derived from three co-occurring column-A signals — indentation
(`alignment.indent` 1–4 = section / group / sub-group / detail), **bold** (every header and
"Total - …" row), and the `Total - {code} - {name}` closers — cross-checked against the
account-number ranges (4xxxxx income, 5xxxxx COGS, 6xxxxx opex, 605xxx O&M, 607000 tax, 607100
insurance). Result: 4 sections → 30 group/sub-group headers → 140 detail lines.

### D-8 — Canonical GL chart: structure, duplicate codes, contra lines, decimals

**Single source of truth.** The chart lives in `gl_accounts` (seeded from
`apps/api/rjacq/seeds/gl_accounts.py`); the Budget tab and OM-mapping both read it — there is no
second GL model. Each node carries `parent_code`, `level` (section/major_group/subgroup/leaf),
`section`, `normal_balance`, `sort`, `default_noi_placement`, and (new) `is_contra` + `tier`.

**Full superset across ALL sheets (not just consolidated).** The consolidated views are *not* a
complete superset — ~10 accounts appear only on per-park sheets, two in nearly every park
(`600145` Payroll Processing Fees in all 27; `605840` Wells One Credit Card in 25). These are
**unioned in** (the "Park-only accounts" block in the seed) so no deal can carry a line that
doesn't map. Each leaf is tagged `tier` = **core** (in ≥60% / 16-of-27 parks) vs **rare**; the
Budget tab can hide rare lines behind a toggle. _(68 core / 72 rare at seed time.)_

**Duplicate codes — key on code + name, never code alone.** `600400` and `600410` are each reused
for two different accounts (Office Expense / Sales & Marketing; Office Software / Travel & Auto).
We keep `account_code` as the primary key and **disambiguate the second occurrence with a `-2`
suffix** (`600400-2`, `600410-2`) — a tiny, additive choice that leaves every existing FK
(`financial_lines`, `budget_lines`, learned mappings) untouched. They should be recoded at source.

**Contra lines — preserve sign, net within the parent.** Seven structural contras are
sign-preserving negative offsets, flagged `is_contra` and summed with their **native negative
sign** (so the group total nets them automatically — no special-casing): `401070` OTA Contra,
`404070` POS Discounts, `421000` Discounts, `421300` Work Camper Credit, `421400` Maint
Opportunity Loss, `605415` Utility Recovery, `605465` Water & Sewer Recovery. Derived from the
**sign in the data** (negative consolidated total), not a keyword scan (which mis-hit
"Contra**ctor**" / "**Credit** Card"). _(Electric 605410 − Utility Recovery 605415 is the basis for
the 62% electric bill-back default.)_ `401200` OTA Notional Clearing is a pass-through, not a
contra.

**Roll-up is pure + unit-tested.** `underwriting/budget.py::roll_up_tree` rolls leaf amounts up the
parent chain to every group/section + NOI (= Total Income − Total Expense; COGS folds into Expense;
below-the-line / non-operating excluded). A worked-example test pins the real Utilities group
(`Total - 605400 = 1,713,517.19`, including the two negative recoveries) from `Consolidated-T-12`.

**Decimals — whole dollars on display, full precision stored.** The source uses `$#,##0.00`. The
Budget tab **displays whole dollars** (read-only subtotals/variance/NOI rounded, negatives in
parentheses); amounts are still stored as full-precision `Decimal` server-side, so no cents are
lost. Editable cells keep their entered value.

---

## 2026-06-29 — AI GL classifier (best-guess + confirm) and OM-seeded prior-year

### D-22 — Claude best-guess GL mapping, gated on confidence (§14 C-20)

The mapping engine already had the confidence-gated scaffold (learned-mapping → classify →
auto-apply if confident, else flag for review), but the classifier was a stub, so every line fell to
manual review. Shipped a Claude-backed classifier (`mapping/providers.py::ClaudeClassifier`, forced
tool use, the GL chart sent as a cache-controlled system block):
- **Claude-only v1 (no Voyage).** It classifies against the full mappable chart (active leaf +
  subgroup accounts) rather than a pgvector shortlist, so it needs only the Anthropic key already
  used for OM extraction — no embedding backfill. The Voyage embedder stays a deferred semantic-
  shortlist optimization.
- **Auto-apply threshold `GL_MAP_AUTO_CONFIDENCE` = 0.6** (config, not baked). At/above → auto-apply
  the guess; below → leave unmapped and surface for review. Human-in-the-loop unchanged: every line
  is still confirmable/overridable, and a hallucinated / off-chart code is rejected to review.
- Default model stays `claude-sonnet-4-6` (classification is a Sonnet task).

### D-23 — Prior-year seeds from the OM, not just an uploaded recap

OM financials already persist (the OM PDF upload runs through `ClaudePdfExtractor → load_pnl`) but
are annual-only, so the month-bucket-only `_prior_actuals` skipped them ($0 prior-year). Made
`_prior_actuals` annual-aware: month columns → sum buckets (recap); otherwise → the line's annual
`amount` (OM / generic P&L). With the classifier auto-mapping the OM lines, an OM-created acquisition
shows a populated prior-year before any P&L; a later recap P&L supersedes it (append-never-overwrite
unchanged).

## 2026-06-29 — OM seeding + Labor roster as the headcount SSOT

Wires offering-memorandum seeding across the Operating, Budget, and Labor tabs with explicit
fallbacks and visible provenance, and makes the Labor roster the single source of truth for
headcount. Seeded values are editable; editing flips the tag to manual.

### D-19 — Seeding map: OM first, stated fallback, provenance on every field

**Decision.** For each seeded field: extract from the OM first (tag **`from OM`** / actuals); if
absent, apply the stated fallback (tag **`default`**) and flag **needs review**; anything neither
sourced nor defaulted stays a **`placeholder`** — never guessed. The full map:

| Tab | Field | From OM | Fallback | Provenance |
|---|---|---|---|---|
| Operating | Annual electric | mapped OM Electric line → 605410 | none → **needs-input** (bill-back can't compute) | from OM / needs-input |
| Operating | Unit mix | OM unit-mix / site_count | default categories, counts blank | from OM / needs-input |
| Operating | Headcount | — reads the Labor roster total | — | *derived* (never stored here) |
| Budget | Prior-year, per line | OM financial lines → canonical GL | blank/flagged | from OM (actuals) / placeholder |
| Labor | Roster (role/count/wage) | OM `staffing` array (roles normalized) | the existing default scenario | from OM / default |
| Labor | Wage per role | OM-stated hourly rate | blank → **needs-input** (required) | from OM / needs-input |

The Budget surface is the existing prior-year/year-one GL grid (extended, not duplicated). Budget
prior-year + Operating electric already sourced from the mapped OM/P&L; this formalizes the tags.
OM extraction gained an optional `staffing` array on the proposal (role/count/hourly_rate).

### D-20 — Headcount single source of truth = the Labor roster

**Decision.** Headcount is **Σ Labor roster counts**, computed by the pure `total_headcount`, and is
**never stored a second time**. The per-employee payroll-budget default and the Operating-tab
display both read it; adding/removing/editing a role recomputes the dependent defaults
automatically (labor mutations call `apply_defaults`) — no manual sync.

- The Operating tab no longer stores or edits headcount; it shows the roster total read-only
  (`source="labor"`). `OperationalInputs.employee_headcount` is **deprecated in place** (kept,
  unread/unwritten) to avoid a destructive migration on live data — to be dropped later.
- **Decision taken with the user:** keep the existing 5-row default roster (3 FT + 2 PT), not the
  brief's 3; wage stays the existing **hourly rate** (now required + surfaced, no engine change);
  rich per-row fields kept behind a `⌄` expander.

### D-21 — Labor roster: provenance + OM seed + required wage

**Decision.** `LaborPosition.source` (om | default | manual; migration `f4a5b6c7d8e9`, additive).
`seed_roster` seeds from OM staffing (tagged `om`, roles mapped via pure `normalize_role`) or the
default scenario (tagged `default`); idempotent. The new-acquisition form seeds the roster from the
OM proposal's staffing at creation. **Wage is required and load-bearing** — it drives both the
headcount-based defaults and the actual labor expense — so a non-work-camper without an hourly rate
is flagged `needs_wage` (a soft flag, not a block).

---

## 2026-06-29 — Budget defaults engine (Parts 1–3)

The configurable rule library that autofills year-one budget line items. Drivers are captured
per property (Part 1); a typed, pure rule engine computes each default (Part 2); the result is
applied onto the budget grid, editable and non-destructive (Part 3). Every autofilled value is
tagged `default` provenance, distinguishable from `actuals` (uploaded) and a manual edit.

### D-15 — Operational inputs: per-deal drivers, captured + provenance-tagged, never guessed

**Decision.** Defaults that depend on counts read from a small per-deal capture: **unit groups**
(`unit_groups`, 1:many) + **headcount** and **electric** (`operational_inputs`, 1:1). Seeded from
the OM unit mix / mapped prior-year Electric where present; a missing driver surfaces a **"needs
input"** prompt and the dependent default reports needs-input rather than computing on a guess.

- **Billable units** = RV pads + cabins + glamping; **tents excluded** (seed `billable=False`).
  The category list is **not** fixed to three — custom sub-types are addable; each group carries
  its own `billable` flag, so the driver is "sum the billable groups' counts".
- Everything editable; an edit flips the field's provenance to `manual`. Migration
  `c9d0e1f2a3b4` (additive).

### D-16 — The rule library: typed, pure, centrally configurable; numbers are data, not logic

**Decision.** Each rule is a `RuleSpec` (type, value/driver, target GL); `compute_default` is a pure
Decimal function, unit-tested with worked examples. `RULE_LIBRARY` is the seed/reset spec; the
numbers live as **data** (and will be DB-overlaid for global in-UI editing), never baked into the
compute logic (CLAUDE.md rule #2). The full table (the confirmed seed values):

| Rule | Type | Value | Driver | GL |
|---|---|---|---|---|
| Insurance | % of gross revenue | 3% | gross revenue | 607100 |
| Credit-card processing | % of gross revenue | 2.5% | gross revenue | 600700 |
| Utilities | % of gross revenue | 17.5% (soft 15–20%) | gross revenue | 605400 |
| Utility bill-back | % of a line | 62% of electric | electric driver | 605415 (contra, **negative**) |
| Repairs & maintenance | per unit (annual) | $275 | billable units | 605100 |
| Property taxes | prior-year uplift | prior × 1.30 (**must-fix**) | prior-year 607000 | 607000 |
| Shield (PMS) | fixed | $1,000/mo | — | 600410 |
| PPC | fixed | $12,000/yr | — | 600225 |
| SEO / subscription marketing | fixed | $850/mo | — | 601010 |
| Active-management marketing | fixed | $825/mo | — | 600210 |
| Call center | fixed | $750/mo | — | 600220 |
| Payroll budget allocation | per employee/mo | $85 × headcount × 12 | headcount | 600145 |

- **Utility bill-back sign = contra-expense (negative).** 62% × electric is posted **negative** to
  605415 Utility Recovery — it nets down the utilities bucket rather than adding revenue.
- **Utilities 17.5% = total utilities incl. electric.** Electric is captured as the bill-back
  **driver only**, not added as a separate above-the-line expense (no double count).
- **PPC is now a fixed $12k/yr** (retires the old site×volume×rate formula).
- **Utilities/insurance/CC % use a gross-revenue base computed ONCE** from projected operating
  revenue, excluding default-generated lines — so a default never feeds back into the % base.
- **Soft warning** (utilities outside 15–20%) flags but never blocks; **must-fix** (property taxes)
  is a persistent placeholder badge.
- **Two additive GL homes** (chart seed): **600145** Payroll Budget Allocation (a budgeted accrual,
  kept distinct from actual wages 600140) and **600220** Call Center. _The call-center home is
  provisional — adjust when the chart is finalized._

### D-17 — Application: gap-fill (subtree-aware) vs override; the bill-back nets down opex

**Decision.** Defaults apply onto `budget_lines` (`source=default`, `default_rule_key`), never
clobbering a manual override. Per rule:

- **Gap-fill (most rules):** post only when the target's **subtree** has no seller actual — a coarse
  default (utilities → parent 605400) is **skipped if the seller mapped detail under it** (e.g.
  electric 605410), so the two never double-count.
- **Override (Shield, property-tax uplift):** supersede a mapped actual on the rule's own account.
- **NeedsInput** posts nothing (the operating panel drives the prompt) — never a guessed number.

### D-18 — Driver-recompute rule: manual sticks; recompute only still-default lines

**Decision (the decision point in the brief).** When a driver (unit count, headcount, electric)
changes **after** a dependent line was manually edited, **the manual value holds** — a driver change
recomputes only lines still tagged `default`. A non-destructive **revert-to-default**
(`POST …/budget/line/{id}/revert-default`) clears the edit and re-links the line to its rule.

**Why.** Matches the existing labor/seed "never clobber `is_overridden`" behavior; deliberate edits
are safe, and the revert gives an explicit, recoverable path back to the computed value.

---

## 2026-06-24 — Labor tab (PRs #65, #66)

### D-14 — Labor plan feeds the budget Wages cluster (+ a work-camper revenue/discount model)

**Decision.** A per-deal **Labor tab** lays out staffing positions; a pure engine rolls them into GL
dollars that drive the budget's year-one Wages lines — so labor flows **budget → NOI → pro forma →
promote**. Prior-year labor is read from the mapped P&L.

- **Flat-lined cost:** wages = hours/week × rate × `active_weeks` (from start/end; FT defaults 40h,
  PT 20h). Week-by-week tuning is a later refinement.
- **Benefits = flat $/eligible employee/month** (config) → GL 600130; **payroll tax = % of wages**
  (config) → GL 600155; **base wages** → GL 600140. The two loads are `[DECISION]`, None-until-set.
- **Work camper = no cash wage.** Comp is the campsite, modeled as **extended-stay revenue (400110)**
  offset by a **Work Camper Campsite Credit (421300)** stored **negative** (contra-revenue): net
  revenue impact = site value − credit. Site rate + credit are per-position.
- **Budget feed** (`budget_service.apply_labor`): writes the five GL year-one values with
  `source=labor`, **never clobbers a human budget override**, FK-safe; editing labor re-feeds and
  invalidates the budget lock. **Default staffing**: 1 GM + 1 front desk + 1 maintenance (FT) + 1
  part-time of the latter two; rates entered per deal.

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

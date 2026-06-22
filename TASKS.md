# Tasks

Working task list for the RJourney Acquisitions Platform. See `PROJECT_STATE.md` for the current
snapshot and `DECISIONS.md` for the rationale behind the choices below.

_Last updated: 2026-06-22._

## Done — underwriting single source of truth (PRs #41–#46)

- [x] **Canonical store schema** — additive columns on `proforma_inputs` + `underwriting_defaults`;
      §8.4 contract brought current (it was missing both tables). _(#41, migration `b2c3d4e5f6a7`)_
- [x] **Read the store in the engines** — `loan_amount` precedence, per-line revenue/expense growth,
      persisted promote terms (co-invest/fees/start-date + `waterfall_tiers`). _(#42)_
- [x] **Recompute on price edit** — `PATCH /acquisitions` routes through the recompute. _(#43)_
- [x] **60-month monthly cash-flow engine** — `build_monthly_cashflows`, `proforma_monthly` table,
      `GET /proforma-monthly`, rollup-equals-annual regression test. _(#44, migration `c3d4e5f6a7b8`)_
- [x] **Pro forma UI** — new fields + the collapsible 60-month grid. _(#45)_
- [x] **Promote persistence** — `GET/PUT /waterfall-tiers`; PromoteTab loads + saves promote terms. _(#46)_

## Done — underwriting page (PRs #48–#54)

- [x] **Auto-map in a worker + seller-scoped learned mappings** — wired `propose_for_line` (it had
      no caller) into a background Arq job after upload; learned per seller with a global fallback. _(#48)_
- [x] **GL mapping confirm workstation** — buckets, GL-chart picker (`GET /gl-accounts`), NOI/learn,
      bulk confirm. _(#49)_
- [x] **Split one seller line across GLs** — `financial_lines.split_parent_id`, pure
      `allocate_split`, `POST …/mapping/split`; merge = confirm-many-to-one. _(#50, migration `d4e5f6a7b8c9`)_
- [x] **Prior-year-vs-year-one budget** — `budgets` + `budget_lines` (editable year-one cells;
      prior-year computed on read from `raw_payload`), grid with variance + provenance + monthly
      expand, seed/patch. _(#51 + #52, migration `e5f6a7b8c9d0`)_
- [x] **Budget lock + flow-through** — `effective_stabilized` precedence manual > locked budget >
      bridge; lock gated on zero placeholders + unmapped; lock/unlock recompute. _(#53)_
- [x] **Defaults engine** — pure Shield / marketing / PPC; formulas in code, numbers in config;
      no-op until configured. _(#54)_

## Next

- [ ] **Deploy to Azure** — the SSOT migrations are live (SHA `8bb2b59`); the next deploy applies the
      Underwriting-page migrations `d4e5f6a7b8c9` + `e5f6a7b8c9d0` (both additive), then rolls
      api/worker/web. Back up Postgres first. Recipe in `docs/DEPLOYMENT.md`
      (`--build-arg BASE_REGISTRY=mirror.gcr.io/library/`).
- [ ] **Activate the defaults engine** — set config: the five `*_account_code` (from the GL chart,
      §14 B-13) + `ppc_rate` / `ppc_target_volume` / `ppc_intercompany_pct`. Until then the budget
      seeds from actuals only. _Needs the GL chart + PPC params from the user._
- [ ] **First-time AI mapping suggestions (§14 C-20)** — build the Voyage embedder + Claude
      classifier so non-learned lines get auto-suggestions (a provider/key + cost decision). Until
      then the worker does learned reuse only.

## Future enhancements (not yet scheduled)

- [ ] **Promote monthly-direct** — run the waterfall on all monthly periods instead of the annual
      rollup (true intra-year distribution timing). Deferred per `DECISIONS.md` D-3; needs a
      monthly-IRR annualization convention so it stays consistent with the annual XIRR.
- [ ] **P&L / T-12 parsing guards (UX)** — the parser is deliberately conservative; these need a
      human confirmation step in the mapping UI:
  - [ ] Confirm **which amount column** is the annualized/stabilized figure on multi-column T-12s.
  - [x] Clear the **GL mapping queue** — the confirm workstation surfaces unmapped lines and the
        budget lock is gated on zero unmapped (#49, #53).
  - [ ] Make **add-backs** (`is_addback` / `addback_amount`) user-editable at confirm time
        (owner salary, one-time items) — currently observed but not editable.
  - [ ] Guard **subtotal rows** and **expense sign** at confirm (double-counting / inverted NOI).
  - [ ] **$ vs $000s scale** detection / confirmation (classic 1000× error).
  - [ ] **Partial-year / fiscal stub** handling — confirm period length before annualizing.
  - [ ] **Monthly seasonalization** — confirm the even-spread assumption for the 60-month grid.
- [ ] Flag **debt terms / hold / start_date** in the UI as user-entered assumptions (no document
      source) so the defaults don't quietly drive returns.

## Older / housekeeping

- [ ] Reconcile the design doc's lingering forest/bone/brass + 3-hurdle references with the shipped
      navy/gold theme and 4-hurdle waterfall.
- [ ] Decide the fate of the legacy `underwriting/engine.py` vs `promote.py`.
- [ ] The GitHub `deploy.yml` auto-deploy has never worked (Azure secrets unset); deploys are manual
      from Cloud Shell.

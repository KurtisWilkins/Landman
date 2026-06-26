# Tasks

Working task list for the RJourney Acquisitions Platform. See `PROJECT_STATE.md` for the current
snapshot and `DECISIONS.md` for the rationale behind the choices below.

_Last updated: 2026-06-24._

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

## Done — chart, review fixes, grid + archive (PRs #56–#63)

- [x] **Full GL chart + defaults wiring** — 169-account RJourney chart seeded; defaults bound to the
      chart codes (Shield 600410, website 600210, secondary 601010, PPC 600225). _(#56)_
- [x] **Over/under review loop** — flag placeholders + >15% variance lines + filter toggle. _(#57)_
- [x] **Adversarial-review fixes** — 8 confirmed correctness bugs. _(#58)_
- [x] **Green-main + seed entry point** — pre-existing test fixes; `rjacq-seed` console script. _(#59, #61)_
- [x] **ProformaTab fast-edit fix** — seed effect no longer clobbers in-flight edits. _(#60)_
- [x] **Two-column GL grid** — editable prior + year-one, TurboTax add/remove of GL/custom (flagged)
      lines, pure NOI roll-up; annual. _(#62, migration `f3a4b5c6d7e8`)_
- [x] **Deal archive (soft-delete)** — `archived_at` flag + restore, ⋯ menu on pipeline rows,
      archived view; no hard-delete anywhere. _(#63, migration `a7b8c9d0e1f2`)_
- [x] **Labor tab** — per-deal staffing plan (positions: type/season/hours/rate/work-camper/
      benefits/dates) → pure cost engine → feeds budget Wages cluster (work campers → extended-stay
      revenue + campsite credit) → NOI → pro forma. Default staffing + the "Labor" tab UI.
      _(#65 backend + migration `b8c9d0e1f2a3`, #66 UI)_

## Next

- [ ] **Deploy to Azure** — prod is live at SHA `b3e4ae4` (grid + archive applied). The next deploy
      applies the labor migration `b8c9d0e1f2a3` (additive), then rolls api/worker/web + re-runs the
      seed. Recipe in `docs/DEPLOYMENT.md` (build via `az acr build`; web from `apps/web`).
- [ ] **Set the labor loads** — `labor_benefits_monthly_per_employee` (→600130) +
      `labor_payroll_tax_pct` (→600155) in config. Until then benefits + payroll tax are $0; wages +
      the work-camper revenue/credit compute fully. _Needs the figures from the user._
- [ ] **Activate the PPC default** — set `ppc_rate` / `ppc_target_volume` / `ppc_intercompany_pct`
      in config (the account codes are already wired, #56). Until then PPC is a no-op; Shield +
      marketing are active. _Needs the PPC params from the user._
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

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

## Next

- [ ] **Deploy to Azure** — run the migrate job (applies `b2c3d4e5f6a7` + `c3d4e5f6a7b8`; both
      additive), then roll api/worker/web. Back up Postgres first (CLAUDE.md). Deploy recipe is in
      `docs/DEPLOYMENT.md` (use `--build-arg BASE_REGISTRY=mirror.gcr.io/library/`).

## Future enhancements (not yet scheduled)

- [ ] **Promote monthly-direct** — run the waterfall on all monthly periods instead of the annual
      rollup (true intra-year distribution timing). Deferred per `DECISIONS.md` D-3; needs a
      monthly-IRR annualization convention so it stays consistent with the annual XIRR.
- [ ] **P&L / T-12 parsing guards (UX)** — the parser is deliberately conservative; these need a
      human confirmation step in the mapping UI:
  - [ ] Confirm **which amount column** is the annualized/stabilized figure on multi-column T-12s.
  - [ ] Clear the **GL mapping queue** — unmapped lines are silently excluded from NOI.
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

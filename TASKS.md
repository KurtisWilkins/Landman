# Tasks

Working task list for the RJourney Acquisitions Platform. See `PROJECT_STATE.md` for the current
snapshot and `DECISIONS.md` for the rationale behind the choices below.

_Last updated: 2026-06-30._

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
- [x] **Flow-through UI** (web-only) — Labor positions get a **Name** field (person filling the
      role); Pro forma shows the **year-1 stabilized (rev/opex/NOI) from the Budget**; Promote shows
      the **acquisition basis (price/equity/debt/LTV) from the pro forma**. No API change.

## Done — budget defaults engine (merged) + OM seeding / headcount SSOT

Budget defaults engine (Parts 1–3 + central config + UI) merged & deployed (`DECISIONS.md`
D-15…D-18). OM seeding + headcount SSOT on the branch (`DECISIONS.md` D-19…D-21):

- [x] **Headcount SSOT** — Labor roster total (`total_headcount`); payroll default + Operating read
      it; labor edits recompute defaults; `OperationalInputs.employee_headcount` deprecated in place.
- [x] **OM seeding map + provenance** — OM `staffing` extraction → `seed_roster` (om/default,
      `LaborPosition.source`, migration `f4a5b6c7d8e9`); wage required (`needs_wage`); tags across
      Operating/Budget/Labor.
- [x] **Web** — Labor roster SSOT UI (banner, provenance badges, `⌄` expander), read-only Operating
      headcount, OM-staffing seed on new-acquisition.

Follow-ups:
- [ ] Drop the deprecated `OperationalInputs.employee_headcount` columns (destructive — backup first).
- [ ] Retire the now-superseded `budget_defaults.py` (+ `test_budget_defaults.py`).
- [ ] Confirm the call-center GL home (600220, under Advertising & Promotion).

## Done — drop Redis/worker; background jobs run in-process (`DECISIONS.md` D-10)

The Arq worker couldn't reach the in-env Redis in prod (internal TCP ingress times out), and
managed Redis is costly for a queue that holds no durable data. Removed it:

- [x] **In-process classifier** — the P&L upload schedules `classify_acquisition_mappings` via
      FastAPI `BackgroundTasks` (runs in the API after the response); job opens its own session and
      never raises into the caller.
- [x] **Removed the queue** — deleted `core/queue.py` (Arq `WorkerSettings` + Redis pool) and the
      `redis_url` config; provision script no longer creates `rjacq-redis`/`rjacq-worker`; `.env.example`
      updated. Deploys roll **api + web** only.
- [x] **Regression test** — `classify_acquisition_mappings` callable with no Arq ctx; graceful on a
      missing acquisition.

Follow-ups:
- [ ] Delete the `rjacq-redis` + `rjacq-worker` Container Apps in prod (no longer used).
- [x] Remove the now-unused `arq` + `redis` dependencies from `apps/api/pyproject.toml` (no lockfile to relock).
- [ ] Wire SHIELD sync to an in-process/admin trigger if/when it's configured (was only ever
      registered on the worker, never enqueued).

## Done — comp discovery: geocode OM address → competitors within 50 mi (`DECISIONS.md` D-9)

Wired the comp-intelligence search end to end (no migration — refresh-replace + raw_payload):

- [x] **Geocoder seam** (`comps/geocode.py`) — Google Geocoding (when keyed) → free Nominatim
      fallback; persists lat/lng on the acquisition; never guesses a location.
- [x] **Real sources** — OpenStreetMap/Overpass (free, always on, full 50-mi `around:` query) +
      Google Places (tiled Nearby Search, deduped) + Campendium/RV LIFE scaffolds **behind
      `scrapers_enabled`** (D-22). Scope broadened to glamping + marinas.
- [x] **Trigger** — `POST …/comps/discover` runs the geocode + radius search **synchronously**
      (no worker/Redis dependency; blocking HTTP off the event loop via `asyncio.to_thread`);
      refresh-replace so re-scans don't duplicate; Comps tab "Find competitors" button.
- [x] **Tests** — pure parse/geometry/tiling-coverage + the geocode→discover service flow (hermetic).

Follow-ups:
- [ ] Provision a Google Maps Platform key (Places + Geocoding) if richer ratings/coverage wanted —
      `GOOGLE_PLACES_API_KEY`. OSM works now without it.
- [ ] Per-site ToS/legal review to flip `scrapers_enabled` and implement the RV-directory scrapers.
- [ ] Enrich comps (rates/sentiment/amenities) — the scatter needs avg_rate which OSM/Google lack.

## Done — canonical GL chart + collapsible Budget tab (`DECISIONS.md` D-8)

Chart of accounts derived from the 31-sheet consolidated income statement; Budget tab mirrors the
source hierarchy with collapse/fold. Migration `f5a6b7c8d9e0`:

- [x] **Canonical chart = full superset** — unioned the ~10 per-park-only accounts the consolidated
      views miss (`600145` Payroll Processing Fees, `605840` Wells One Credit Card, …) into the seed
      so no deal can carry a line that doesn't map (180 rows).
- [x] **Chart metadata** — `gl_accounts.is_contra` (7 structural contras, sign preserved → net in
      parent) + `tier` (core/rare, keyed on park-presence); backfilled idempotently at seed time.
      Duplicate codes (`600400`/`600410`) keep `account_code` PK via the `-2` suffix.
- [x] **Pure hierarchical roll-up** — `underwriting/budget.py::roll_up_tree` (section→group→leaf +
      NOI), unit-tested against the workbook's own totals incl. the Utilities contra recoveries.
- [x] **Budget API** — `GET /budget` returns group subtotals + per-row hierarchy; `/gl-accounts`
      returns `parent_code`/`sort`/`is_contra`/`tier`.
- [x] **Budget tab UI** — collapsible section → group → sub-group → detail; Total closes every group
      (visible when collapsed); collapse-all/expand-all; hide-rare toggle; parentheses for negatives;
      whole-dollar display; NOI at the bottom.

Follow-ups:
- [ ] Recode the duplicate `600400-2` / `600410-2` at source (drop the `-2` convention).
- [ ] Optionally render the full chart (zero rows) when expanded, not just accounts with data.

## Next

- [ ] **(Optional) Draft budget → pro forma without locking** — today the year-1 budget feeds the
      computed pro forma only when the budget is **locked** (`effective_stabilized`: manual > locked
      budget > P&L bridge, D-11). The Pro forma card now shows draft year-1 for reference but the
      calc still uses the bridge until lock. Decide whether a draft budget should drive the calc.

- [x] **Deploy to Azure** — prod is live at SHA `3395d20` (api `--0000042`, worker `--0000029`);
      migration `f4a5b6c7d8e9` (`labor_positions.source`) applied. The first attempt's migration had
      a duplicate revision id (`e1f2a3b4c5d6`) → cycle → migrate failed; #72 renamed it and the
      re-deploy applied it. Deploy command now hard-gates on the migrate job's `Succeeded` status
      before rolling apps. Recipe in `docs/DEPLOYMENT.md` (build via `az acr build`; web from `apps/web`).
- [ ] **Set the labor loads** — `labor_benefits_monthly_per_employee` (→600130) +
      `labor_payroll_tax_pct` (→600155) in config. Until then benefits + payroll tax are $0; wages +
      the work-camper revenue/credit compute fully. _Needs the figures from the user._
- [ ] **Activate the PPC default** — set `ppc_rate` / `ppc_target_volume` / `ppc_intercompany_pct`
      in config (the account codes are already wired, #56). Until then PPC is a no-op; Shield +
      marketing are active. _Needs the PPC params from the user._
- [x] **First-time AI mapping suggestions (§14 C-20)** — Claude best-guess classifier shipped:
      `build_classifier()` runs against the full mappable chart (no Voyage needed), auto-applies a
      guess at/above `GL_MAP_AUTO_CONFIDENCE` (0.6) and flags the rest for review; gated on the
      Anthropic key. _Follow-up:_ the Voyage embedder + `GLAccount.embedding` backfill for a semantic
      shortlist (accuracy/cost optimization), and batching the per-line classify calls.
- [x] **Prior-year seeded from the OM** — `_prior_actuals` is now annual-aware (uses the line's
      annual `amount` when there are no per-month columns), so OM-extracted financials populate
      prior-year before any P&L upload; a later recap P&L supersedes them.

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

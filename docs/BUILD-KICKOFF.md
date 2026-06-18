# Build Kickoff — Orchestrator Prompt & Parallel Streams

How to start the build with Claude Code. **Phase 0 is a hard gate:** one session lands the
foundation and freezes the contract; only then do the four streams run in parallel.

---

## Mechanics (read first)

1. **One foundation session.** Run the orchestrator prompt (below) in a single Claude Code
   session. It plans, then builds **Phase 0 only** and opens one PR. Review and merge it.
   Phase 0 freezes: the §8 schema + migrations, `core/` utilities, auth/RBAC, CI, and the §9
   API surface as **typed stubs + OpenAPI + generated TS types**. This last part lets the
   frontend stream build against the contract before the backend logic exists.
2. **Then fan out with git worktrees.** Create one worktree + branch per stream and run each in
   its **own** Claude Code session with its brief. Worktrees keep the working trees isolated so
   parallel sessions don't collide:
   ```bash
   git worktree add ../rjacq-ingestion  -b feat/ingestion-mapping
   git worktree add ../rjacq-underwrite -b feat/shield-underwriting
   git worktree add ../rjacq-comps      -b feat/comp-intelligence
   git worktree add ../rjacq-frontend   -b feat/frontend-gates-feedback
   ```
3. **Disjoint by design.** Each stream owns separate folders (below). The only shared seams are
   the frozen schema/migrations and the OpenAPI contract — treat any change to those as a
   coordination point that pauses for review, not a unilateral edit.
4. **Integrate continuously.** Each stream opens its own PR against `main`; the auto-review
   workflow comments, a human merges. Rebase streams on `main` as PRs land.

---

## Orchestrator prompt (foundation session)

```
You are bootstrapping the RJourney Acquisitions Platform. The repo root contains:
- docs/rjourney-acquisitions-design-document-v0.2.md  ← THE SPEC. §8 is the data contract.
- CLAUDE.md ← how we build (non-negotiable). README.md, CONTRIBUTING.md
- .github/ workflows + issue/PR templates, .env.example, docs/adr/0001-…
- rjourney-acquisitions-wireframes.html ← visual reference for the frontend

Step 1 — Understand & plan. Read all of the above. Produce a build plan that follows the
design doc §11 phases. List every [DECISION] item you'll hit; per CLAUDE.md, do NOT invent
values — scaffold against named config/env placeholders with `# TODO(decision: §14 ref)` and
keep going. Show me the plan and the [DECISION] list before writing code.

Step 2 — Phase 0 only (the gate). Build the foundation on a branch and open ONE PR:
monorepo layout (apps/api, apps/web, migrations), Postgres+pgvector, Alembic migrations for
the FULL §8 schema (acquisitions, financials, property/ops, underwriting, comps, gates, feedback),
seed gl_accounts from the chart in §8.5 and the gate_questions, core/ (config, structured
logging w/ correlation IDs, auth skeleton via Entra OIDC + external fallback, RBAC, S3
client, Sentry init), Redis/Arq queue wiring, the Makefile and docker-compose so
`make bootstrap` / `make dev` / `make migrate` / `make test` actually work, CI that runs
lint+test, and — important — the §9 API surface as typed FastAPI stubs with a generated
OpenAPI schema and TypeScript types, so the frontend stream can build against the contract
before the logic exists. Do NOT start Phases 1–4 until I review and merge Phase 0.

Step 3 — After Phase 0 merges, fan out. The four streams touch disjoint folders and all code
against the frozen §8 schema and the §9 OpenAPI contract. I'll run each as its own Claude Code
session in a separate git worktree; each owns its branch and opens its own PR. Use the
per-stream briefs in docs/BUILD-KICKOFF.md.

Rules for everything: conform to §8; obey CLAUDE.md (provenance, human-in-the-loop, read-only
SHIELD, no guessed [DECISION] values, no browser storage, Decimal/cents for money); tests with
new logic (worked examples for IRR/waterfall/NOI); Conventional Commits; small PRs linked to
issues; no auto-merge. Check in with me after the plan, after Phase 0, and after each stream PR.
```

---

## Stream A — Ingestion & GL mapping  (Phase 1)
**Owns:** `apps/api/ingestion/`, `apps/api/mapping/`. Mapping-review UI hooks coordinate with Stream D via the OpenAPI contract.

```
Build Phase 1 (design doc §5.2–5.3) against the frozen §8 schema. Scope:
- Document parsing: Excel/CSV via pandas/openpyxl with sheet-type detection (P&L, unit mix,
  rent roll, booking export); PDF via a Claude extraction module returning schema-valid JSON;
  one normalized load routine for all paths; retain originals in raw_payload.
- GL mapping engine: embed gl_accounts descriptions into pgvector once; for each seller line,
  shortlist top 3–5 by cosine similarity, have Claude pick the account, the level it can
  justify (leaf vs subgroup), a confidence score, and NOI placement; degrade gracefully to the
  subgroup ('coarse') when the source lacks granularity; store unmapped lines with null
  account; write confirmed mappings to gl_mappings_learned and reuse them.
- NOI bridge: exclude below-the-line (700000/800000) and detected owner add-backs from
  normalized NOI; record the reconciliation.
- Expose the mapping-review + confirm endpoints from §9.
Tests required: leaf/coarse/unmapped degradation, learned-mapping reuse, NOI add-back exclusion.
Follow CLAUDE.md. Open a focused PR.
```

## Stream B — SHIELD + underwriting  (Phase 2)
**Owns:** `apps/api/shield/`, `apps/api/underwriting/`.

```
Build Phase 2 (design doc §5.4–5.5) against the frozen §8 schema. Scope:
- SHIELD connector: READ-ONLY SQL Server access; a scheduled job pulls portfolio actuals and
  aggregates baseline metrics to seed each acquisition's assumptions; keep a SHIELD schema snapshot
  and flag drift. Which metrics is [DECISION C-15] — read keys from config.
- Pro forma engine: 5-yr levered cash flow (Revenue → OpEx → NOI → Debt Service → CapEx →
  Levered CF) + Year-5 exit on an exit cap; metrics: levered IRR, equity multiple, going-in
  cap, Yr-1 cash-on-cash; 3-hurdle equity waterfall with per-tier LP/GP splits; assumptions
  carry baseline + override + author + note; hurdle thresholds from config with per-acquisition
  override and pass/fail. Default thresholds/splits are [DECISION A-1/A-2] — config, not
  literals.
- Recalculate on assumption change; expose §9 proforma + assumptions endpoints.
Tests required: worked IRR, waterfall tiering, and NOI examples; Decimal/cents money only.
Follow CLAUDE.md. Open a focused PR.
```

## Stream C — Comp intelligence  (Phase 3)
**Owns:** `apps/api/comps/`, the scraper service.

```
Build Phase 3 (design doc §5.6) against the frozen §8 schema. Scope:
- Discovery: RV parks/campgrounds within a 50-mile radius of the acquisition address (Google Places).
- Source connectors behind one interface: official APIs where available (Google, Yelp,
  TripAdvisor), Playwright scrapers for niche sites (Campendium/Camp Media, The Dirt). API vs
  scraping per source is [DECISION D-22]; gate scrapers behind a config flag and log
  success/failure per source. Manual add by URL or direct entry.
- Per comp: rate, amenities, best+worst sentiment snippets + score; Claude-generated amenity
  description, score, and market rank with rationale; retain raw_payload.
- Expose §9 comp endpoints incl. visualization data (rate×sentiment, rate×amenities).
Respect robots/ToS; do not scrape sites pending legal review — leave them behind the flag.
Tests required: radius filtering, per-source connector contract, manual-add enrichment.
Follow CLAUDE.md. Open a focused PR.
```

## Stream D — Frontend, gates & feedback  (Phase 4)
**Owns:** `apps/web/`, `apps/api/gates/`, `apps/api/feedback/`. Builds against the OpenAPI contract; uses stubs until A/B/C land.

```
Build Phase 4 (design doc §5.7–5.12, §6, §7) against the frozen §9 contract and §8 schema. Scope:
- Responsive shell: left rail (desktop) ↔ bottom tab bar (mobile), identical destinations;
  match the wireframe design tokens; mobile-first. No browser storage.
- Screens: Pipeline dashboard (phase buckets + rolled-up $), Acquisition detail (Pro forma / Comps /
  Gates / GL-Docs tabs), GL mapping queue, Approvals, Feedback triage. Charts via Recharts.
  Pro forma renders on mobile ([DECISION A-5]: implement horizontal-scroll now, leave a hook
  for a condensed card view).
- Gates: configurable gate_questions, suggest→approve queue (admin approves), blocking logic
  that prevents phase skips, email routing internal/external with an RMS placeholder.
- Feedback: floating "?" widget on every page → feature/bug/question with silent context
  capture (route, acquisition, role, version, browser, breadcrumbs, console + last API error,
  optional screenshot); triage queue; "Dispatch to Claude Code" → create a GitHub issue with
  the enriched brief + @claude; webhook syncs PR/issue status back. No auto-merge.
- Observability: wire Sentry (front) tagged by release; ensure the breadcrumb buffer feeds bug
  reports.
Tests required: gate blocking logic, suggest→approve flow, feedback context capture + dispatch.
Follow CLAUDE.md. Open focused PRs (frontend and the two API modules can be separate PRs).
```

---

## Sequencing notes
- Run the orchestrator → review the plan + [DECISION] list → merge Phase 0 before any stream.
- Resolve the Phase-0 blockers (§14: C-14, C-16, C-17, C-20, B-13, C-28, C-29) before or during
  Phase 0; record each as an ADR.
- Streams B and D are the long poles. D can start immediately against stubs; B unblocks the
  numbers D renders. A unblocks the mapping-review screen in D. C is the most independent.
```

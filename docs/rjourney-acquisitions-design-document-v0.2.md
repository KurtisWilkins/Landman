# RJourney Acquisitions Platform — Design Document (v0.2)

**Audience:** Claude Code (build agent) and the RJourney engineering team.
**Purpose:** Single, self-contained source of truth to build a web application that ingests
acquisition documents, normalizes them, underwrites deals, scrapes a competitive set, tracks
a phase-gated pipeline, and carries its own in-app feedback loop and observability.

This document supersedes v0.1 and the separate schema/addendum/checklist files; everything is
consolidated here.

---

## 0. How to use this document

- §8 (Data model) is the **canonical data contract**. Where any section conflicts with §8 on data *shape*, §8 wins. This document wins on *behavior* and *architecture*.
- Items marked **[DECISION]** are unresolved. Do not hard-code a guess — read the value from config and surface it; the full list is in §14.
- Build order is in §11. The data model is the shared contract that lets the modules be built largely in parallel.

---

## 1. Problem & goals

RJourney evaluates dozens of RV-resort / campground acquisitions per week (3–30). Source
material arrives as messy PDFs, Excel files, and CSVs with no common format. The team needs
to extract and normalize that material into one schema, underwrite against RJourney's own
operating actuals (from the SHIELD database), benchmark each target against its local market,
and move each deal through a gated pipeline (Initial UW → LOI → Contract → Due Diligence →
Close) with a configurable question framework and human-in-the-loop review.

**Success looks like:** a deal lands by email, gets parsed and mapped automatically, a
first-pass normalized pro forma and comp set are generated for human review, and the deal is
trackable from a phone at 2 a.m. through to close or kill — with a feedback widget and logging
that flag problems before users hit them.

## 2. Users & access

| Role | Who | Capabilities |
|---|---|---|
| Admin / Operator | Kurtis (President of Operations) | Everything; approves gate-question changes; overrides assumptions; advances/kills deals; triages & dispatches feedback |
| Executive | CEO | Full read; advance/kill; comment |
| Equity partner | Private-equity reviewers | Scoped read on shared deals; comment; answer routed questions |
| Analyst / staff | Smaller internal users | Upload, answer questions, suggest gate items, submit feedback |

- **Auth:** Microsoft Entra ID (Azure AD) SSO via OIDC for internal users ("Windows login"); a secondary method (email magic-link or password) for external PE partners. Role-based access control (RBAC). **[DECISION]** confirm IdP + external method.
- **Hosting:** public web app behind login. **[DECISION]** cloud provider (Azure aligns with Entra; AWS also fine).
- Mobile-first, desktop-parity (§6). Browsers: Chrome, Brave, Safari.

## 3. Non-negotiables

1. **Mobile-first, desktop-consistent.** Same information hierarchy and navigation on both; responsive reflow, not a separate app. Muscle memory must transfer between phone and browser.
2. **Pro forma on every device.** Full 5-year levered cash flow, IRR, equity multiple, and the 3-hurdle waterfall must render on mobile (horizontal scroll or condensed card view — **[DECISION]**).
3. **Greedy ingest, graceful degradation.** Capture all detail offered; roll up to summary when detail is missing; never fail an ingest for missing granularity.
4. **Human-in-the-loop.** AI proposes (mappings, extractions, comp scores, first-pass pro forma, feedback fixes); a human accepts. Nothing locks or ships without review.
5. **Configurable gates.** Question sets per phase live in config, editable in-app. Anyone may *suggest*; only the Admin *approves*.
6. **Provenance everywhere.** Every financial line keeps its original seller text, mapped account, confidence, and NOI placement. Every assumption keeps baseline vs. override and who changed it.
7. **Know before users do.** Operational logging, error tracking, and alerting are first-class, not an afterthought (§7).

## 4. Architecture

```
                        ┌──────────────────────────┐
   Browser (mobile/     │  Frontend  (React + TS)  │
   desktop, responsive) │  responsive SPA + "?"     │
                        │  floating feedback widget │
                        └────────────┬─────────────┘
                                     │ HTTPS / JSON
                        ┌────────────┴─────────────┐
                        │  API  (FastAPI, Python)   │
                        │ auth·deals·proforma·gates │
                        │ comps·mapping·feedback     │
                        └──┬─────┬─────┬─────┬───────┘
                           │     │     │     │
        ┌──────────────────┘     │     │     └────────────────────┐
        │                        │     │                          │
 ┌──────┴──────┐        ┌────────┴───┐ │                  ┌───────┴────────┐
 │ PostgreSQL  │        │ Job queue  │ │                  │ Object storage │
 │ + pgvector  │        │ (workers)  │ │                  │ files·photos·  │
 └─────────────┘        └──┬─────┬───┘ │                  │ screenshots    │
                           │     │     │                  └────────────────┘
                ┌──────────┘     │     └──────────┐
        ┌───────┴────────┐ ┌─────┴───────┐ ┌──────┴───────────┐
        │ Ingestion      │ │ Scraper svc │ │ AI services       │
        │ Excel/CSV/PDF  │ │ (Playwright)│ │ Claude API + embed│
        └───────┬────────┘ └─────────────┘ └───────────────────┘
                │
   ┌────────────┼───────────────┬─────────────────────────────┐
┌──┴──────────┐ ┌───────────────┴───┐ ┌──────────────────┐ ┌──┴────────────────┐
│ Email intake│ │ SHIELD connector  │ │ Observability    │ │ GitHub + Claude    │
│ deal mailbox│ │ read-only SQLSrvr │ │ logs·Sentry·     │ │ Code Action        │
└─────────────┘ │ → baseline sync   │ │ metrics·alerts   │ │ (feedback dispatch)│
                └───────────────────┘ └──────────────────┘ └────────────────────┘
```

### Recommended stack (with rationale)

- **Frontend:** React + TypeScript (Vite), Tailwind CSS, TanStack Query, React Router, Recharts (scatter/bar/waterfall). The wireframe is already React-shaped; Tailwind gives responsive parity cheaply.
- **Backend:** Python + FastAPI. Ingestion is Excel/CSV/PDF (pandas/openpyxl are first-class); the AI mapping/extraction lives here too.
- **Database:** PostgreSQL with **pgvector** (stores GL-account embeddings for the mapping engine).
- **Workers / queue:** async task runner (Arq, RQ, or Celery) for ingest, scraping, SHIELD sync, and feedback dispatch jobs.
- **Object storage:** S3-compatible (AWS S3 or Cloudflare R2) for source files, gallery photos, and feedback screenshots.
- **AI:** Anthropic Claude API for PDF extraction, GL classification, comp sentiment/amenity summaries, and first-pass narrative. An embeddings model (e.g. Voyage) for the mapping shortlist. **[DECISION]** provider + key ownership.
- **SHIELD:** read-only SQL Server connection (pyodbc / SQLAlchemy); a scheduled job syncs baseline metrics into the `assumptions` seed. **[DECISION]** connection + which metrics.
- **Scraping:** Playwright (headless); official APIs where available (Google Places, Yelp Fusion, TripAdvisor Content API), scraping for niche sites (Campendium/Camp Media, The Dirt). **[DECISION]** API keys vs. scraping + ToS/legal review.
- **Auth:** Entra ID OIDC + secondary external method; RBAC middleware.
- **Email intake:** dedicated mailbox via Microsoft Graph, or inbound parse (Postmark/SendGrid). **[DECISION]** provider.
- **Feedback dispatch:** GitHub API + official `anthropics/claude-code-action@v1` (§5.12).
- **Observability:** structured JSON logging, Sentry (front + back), metrics dashboard, alerting (§7).

---

## 5. Feature modules

### 5.1 Deal intake & email ingestion
A dedicated deal mailbox is monitored; new mail creates a `deals` record in `initial_uw` with
attachments stored to object storage and queued for parsing. Manual upload from the UI does
the same. A deal can accept more documents at any phase.

### 5.2 Document parsing
- **Primary path: Excel/CSV.** Parse with pandas/openpyxl. Detect sheet type (P&L, unit mix, rent roll, booking export) via header heuristics + a Claude classification pass when ambiguous.
- **Secondary path: PDF.** Route to a Claude extraction module returning structured JSON conforming to §8; validate before load. Keep the original in `raw_payload`.
- All paths converge on the same normalized load routine.

### 5.3 GL mapping engine (core)
1. Embed every `gl_accounts` description once (pgvector).
2. For each incoming seller line, retrieve top 3–5 candidate accounts by cosine similarity.
3. Claude picks from the shortlist, returns target account, the **level it can justify** (leaf vs. subgroup), a confidence score, and **NOI placement** (above/below/non-operating).
4. **Granularity degradation:** if the source can't justify a leaf (e.g. one "Marketing" line vs. eight sub-accounts), map up to the subgroup and tag `coarse`.
5. **Learned mappings:** when a human confirms a mapping, store `seller_phrase → account_code` in `gl_mappings_learned`; future files from that seller / phrasing auto-resolve.
6. **Unmapped** lines are stored with a null account and surfaced for review — never dropped.
7. **NOI bridge:** lines tagged below-the-line (Debt Service 700000, Non-Operational 800000) and detected owner add-backs are excluded from normalized NOI; the bridge object records the reconciliation.

### 5.4 SHIELD assumptions layer
- Scheduled read-only query of SHIELD pulls RJourney portfolio actuals (occupancy, ADR, OpEx ratio, RevPAU, etc. — **[DECISION]** exact set) at transaction-level detail, aggregated to baseline metrics.
- Baselines seed each deal's `assumptions`; the operator may override per deal, with the override, author, and note retained.
- Maintain a schema snapshot of SHIELD so the connector flags drift if SHIELD changes.

### 5.5 Underwriting / pro forma engine
- 5-year levered cash flow: Revenue → OpEx → **NOI** → Debt Service → CapEx reserve → Levered CF, plus a Year-5 exit on an exit-cap assumption.
- Metrics: levered IRR, equity multiple, going-in cap, Year-1 cash-on-cash.
- **3-hurdle equity waterfall** with LP/GP promote splits per tier (`waterfall_tiers`).
- **Hurdles:** default thresholds (config) with per-deal override; each renders pass/fail.
- Recalculates live when an assumption changes; flags which inputs were overridden from the SHIELD baseline. **[DECISION]** real default hurdle values and promote splits.
- **Population rings (market sizing).** Estimated population within **25 / 50 / 100 / 150 miles** of the property, part of the Initial UW specs. Auto-pulled from a demographics provider when a property is entered, and overridable by the underwriter (baseline + override + author + note retained, like assumptions). Stored in `population_rings` (§8.4). The wired provider is **US Census ACS** (county-grain, **ADR-0009**): each ring sums ACS 5-year population for counties whose centroid falls within the radius, configured via `POPULATION_PROVIDER=census` + a free Census key. With no provider, rings are entered manually — never fabricated; a ring capturing no county centroid is left unestimated rather than zeroed.

### 5.6 Comp intelligence
- On a deal's address, discover RV parks / campgrounds within a **50-mile radius**.
- Pull rate, amenities, and review sentiment from Google, TripAdvisor, Yelp, Campendium/Camp Media, The Dirt (official APIs + scraping).
- **Sentiment:** capture best and worst representative snippets per comp, plus a score.
- **Amenities:** Claude generates a per-comp description and an amenity score + market rank, each explained.
- **Manual add:** operator adds a competitor by URL or direct entry; system scrapes/enriches it.
- Visuals: rate × sentiment scatter (toggle to rate × amenities), rate bar chart, ranked amenity list, target highlighted.

### 5.7 Phase gates & question framework
- Phases: `initial_uw` → `loi` → `contract` → `due_diligence` → `close`. A deal cannot skip; it advances only when all blocking items for the current phase are green, after AI pre-check then human review.
- Gate questions live in `gate_questions` (config), grouped by category. Seed Initial UW (P&L + unit mix), LOI (attorneys looped, deal points), Due Diligence (the RV-remastered checklist — **[DECISION]**), Close (operational "can we run it better?").
- **Suggest → approve:** anyone submits to `question_suggestions`; Admin approves/declines; approved items join the live set going forward without disturbing historical deals.
- **Routing:** an item can be routed internal or external (e.g. tax person, environmental firm) — initially via **email**, with a **placeholder integration point for the RMS ticketing system**.
- Failed deals drop to a `failed` / `on_ice` queue and remain retrievable.

### 5.8 Pipeline dashboard & deal detail
- Mobile landing = pipeline: phase buckets with deal counts and rolled-up acquisition dollars, then deal lists with blocker chips.
- Deal detail: header with phase progress, then tabs — Pro forma, Comps, Gates, GL/Docs.
- Visual reference: the approved wireframe (`rjourney-acquisitions-wireframes.html`).

### 5.9 Media gallery
Photos auto-pulled from the park website and Google (customer photos with review snippet),
plus seller-provided and manual uploads, displayed as a gallery on the deal — primarily to
orient equity reviewers.

### 5.10 Floating feedback widget
A persistent **"?" floating button** on every authenticated page (bottom-right desktop,
thumb-reachable mobile), part of the responsive shell so it never blocks content. Three
actions: **Request a feature**, **Report a bug**, **Ask a question**.

Context auto-captured silently on every submission: current route + `deal_id` if on a deal,
user, role, timestamp, app version/build hash, browser, OS, viewport. For bugs additionally:
optional screenshot, recent **client breadcrumbs**, captured **console errors**, and the
**last API error**. The user types only a short description. Writes a `feedback_items` record.
**[DECISION]** screenshots may contain deal financials — confirm capture/redaction policy.

### 5.11 Triage & review queue (Admin)
A queue where the Admin reviews every submission.
- Board by status: `new → triaged → needs_detail → ready → dispatched → in_progress → deployed → closed` (plus `declined`).
- Shows captured context inline (page, role, version, logs, screenshot).
- Set type (feature / bug / deployment), priority, tags; link related items.
- **Enrich it:** add comments to build the context — repro steps, desired behavior, affected screen, links. The accumulated brief is what gets handed to Claude Code, so richer items produce better PRs. Item reaches `ready` only when the brief is complete enough to act on.

### 5.12 Agentic dispatch to Claude Code
From a `ready` item, **"Dispatch to Claude Code"** packages context and hands it to the build
agent via GitHub.

1. Backend assembles a structured brief: title, type, description, page route + deal context, repro steps, attached logs / Sentry link / screenshot URLs, enrichment notes, affected-area hints.
2. Backend creates a **GitHub issue** via the API with the brief, the right label, and an **`@claude`** mention with scoped instructions.
3. The official **`anthropics/claude-code-action@v1`** workflow picks up the mention, reads the repo and `CLAUDE.md` standards, implements on a branch, and opens a **PR referencing the issue**.
4. A GitHub webhook syncs issue/PR state back to `feedback_dispatch` (issue URL, PR URL, status); the queue reflects `in_progress → pr_open → merged → deployed` automatically.
5. On deploy the item closes; optionally notify the submitter.

**Iteration:** add another comment to the issue (more context / corrections) and re-mention
`@claude`; the feedback item accumulates the thread. Re-dispatch as needed.

**Guardrails (do not skip):**
- **Review-first, no auto-merge.** Branch protection requires human approval of every Claude-authored PR before it ships.
- Enable write-enabled `@claude` only after branch protection, path filters, and trigger rules are defined; start in review/triage mode and expand.
- Workflow permissions limited to need (`contents`, `pull-requests`, `issues`, `id-token`); `ANTHROPIC_API_KEY` in repo secrets. **[DECISION]** key ownership + spend cap.

Minimal trigger illustration (the build agent will harden this):
```yaml
# .github/workflows/claude.yml
on:
  issues: { types: [opened, assigned] }
  issue_comment: { types: [created] }
permissions:
  contents: write
  pull-requests: write
  issues: write
  id-token: write
jobs:
  claude:
    runs-on: ubuntu-latest
    if: contains(github.event.issue.body, '@claude') || contains(github.event.comment.body, '@claude')
    steps:
      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
```
Reference: Claude Code GitHub Actions — https://code.claude.com/docs/en/github-actions

---

## 6. Frontend spec
- Responsive shell: left rail (desktop) ↔ bottom tab bar (mobile); identical destinations. The "?" feedback button lives in the shell on all pages.
- Design tokens from the wireframe (forest ink, bone paper, brass accent, mono for figures). Match it.
- Screens: Pipeline, Deal detail (Pro forma / Comps / Gates / GL-Docs tabs), GL mapping queue, Approvals, Feedback triage. Charts via Recharts.
- Accessibility floor: visible keyboard focus, reduced-motion respected, mobile-sized tap targets.

## 7. Observability, logging & alerting
Goal: **know what's wrong before users do.** Operational telemetry, distinct from the business
audit/provenance trail.
- **Structured logging.** JSON logs across API and workers with a request/correlation ID threaded through each flow. Log ingest jobs, GL mapping decisions, scrape runs (per source), SHIELD syncs, auth events.
- **Error tracking.** Sentry (or equivalent) on frontend **and** backend, tagged with release/build hash so every error ties to a deploy; captures stack traces and breadcrumbs. **[DECISION]** provider + data-residency.
- **Client breadcrumbs feed the widget.** The same breadcrumb buffer powering Sentry is what the bug-report path attaches automatically.
- **Metrics & dashboards.** Request latency, error rate, background-job success/failure, queue depth, **scrape success rate per source**, ingest failure rate, **SHIELD sync health** (Prometheus + Grafana, or hosted APM).
- **Proactive alerts.** Notify the team (Slack / email) on error-rate spikes, repeated job failures, a broken scrape source, or a failed SHIELD sync. **[DECISION]** alert channel.
- **Synthetic checks.** Uptime probes on critical flows (login, deal load, pro forma calc).
- **Trace the loop.** Link Sentry issue ↔ `feedback_item` ↔ GitHub issue/PR so a runtime error, the user report, and the fix are one thread.

---

## 8. Data model (canonical contract)

### 8.1 Design principles
- **Greedy ingest, graceful degradation.** Capture every level offered; roll up when detail is missing; never fail on missing granularity.
- **Granular + rollup, side by side.** Raw booking transactions stored *and* pre-aggregated into weekly summaries. Drill down to audit; analyze on the rollup.
- **Every financial line carries provenance.** Original seller line, mapped account, level, confidence, NOI placement.
- **Baseline vs. override always visible.** Assumptions record SHIELD baseline and any override with author + note.
- **The schema versions.** Reference data (GL chart, gate questions) is config, not code; `raw_payload jsonb` holds anything not yet formalized.
- Storage: **PostgreSQL**. SHIELD (SQL Server) is an external read-only source.

### 8.2 Enums / controlled vocabularies

| Field | Allowed values |
|---|---|
| `property_type` | `rv_resort`, `campground`, `glamping`, `cabin_resort`, `marina`, `mobile_home`, `hybrid` |
| `current_phase` | `initial_uw`, `loi`, `contract`, `due_diligence`, `close` |
| `status` (deal) | `active`, `failed`, `on_ice`, `closed` |
| `photo.source` | `website`, `google`, `seller`, `manual` |
| `account_level` | `section`, `major_group`, `subgroup`, `leaf` |
| `map_confidence` | `leaf`, `coarse`, `unmapped` |
| `noi_placement` | `above`, `below`, `non_operating` |
| `unit_type` | `rv_pull_through`, `rv_back_in`, `cabin`, `park_model`, `tent`, `glamping`, `marina_slip`, `rv_storage` |
| `hookup_level` | `full`, `water_electric`, `partial`, `dry`, `na` |
| `amp_rating` | `20`, `30`, `50`, `null` |
| `channel` | `direct`, `ota`, `phone`, `walk_in`, `membership` |
| `weekly_summary.source` | `computed`, `seller_provided` |
| `gate_item.status` | `open`, `requested`, `received`, `accepted`, `waived`, `failed` |
| `route_type` | `internal`, `external` |
| `suggestion.type` | `add`, `retire`, `edit` |
| `feedback.type` | `feature`, `bug`, `question` |
| `feedback.status` | `new`, `triaged`, `needs_detail`, `ready`, `dispatched`, `in_progress`, `deployed`, `closed`, `declined` |

### 8.3 Canonical JSON deal document

```jsonc
{
  "deal_id": "dl_cedarhollow_0425",
  "schema_version": "0.2",

  "metadata": {
    "name": "Cedar Hollow RV Resort",
    "property_type": "rv_resort",
    "address": { "line1": "412 Cedar Hollow Rd", "city": "Asheville", "state": "NC",
      "zip": "28806", "lat": 35.5951, "lng": -82.6040 },
    "site_count": 182, "ask_price": 14200000, "price_per_site": 78021,
    "seller_name": "Hollow Holdings LLC", "date_received": "2025-04-09",
    "current_phase": "due_diligence", "status": "active",
    "thesis": "Underpriced vs. hookup quality; low-capex amenity lift.",
    "notes": "Owner retiring; motivated. Septic age unknown."
  },

  "photos": [
    { "source": "website", "url": "https://...", "caption": "Pool & clubhouse", "sort": 1 },
    { "source": "google",  "url": "https://...", "caption": "Guest photo — riverside",
      "review_snippet": "Loved the back-in spots by the water" },
    { "source": "seller",  "url": "https://...", "caption": "Aerial site map" }
  ],

  "financials": {
    "periods": [ { "period_id": "fp_t12_2024", "label": "T12 2024",
      "start": "2024-01-01", "end": "2024-12-31", "granularity": "t12" } ],
    "lines": [
      { "period_id": "fp_t12_2024", "account_code": "400100", "account_level": "subgroup",
        "amount": 2680000, "seller_source_line": "Site Rental Income",
        "map_confidence": "leaf", "map_confidence_score": 0.98, "noi_placement": "above",
        "is_addback": false, "addback_amount": 0,
        "reviewed_by": "kurtis", "reviewed_at": "2025-05-28T14:02:00Z" },
      { "period_id": "fp_t12_2024", "account_code": "600200", "account_level": "subgroup",
        "amount": 96000, "seller_source_line": "Marketing",
        "map_confidence": "coarse", "map_confidence_score": 0.74, "noi_placement": "above" },
      { "period_id": "fp_t12_2024", "account_code": null, "account_level": null,
        "amount": 84000, "seller_source_line": "Owner Debt Service",
        "map_confidence": "unmapped", "noi_placement": "below",
        "is_addback": true, "addback_amount": 84000 }
    ],
    "noi_bridge": { "reported_net_income": 1402000, "addbacks": 124000,
      "non_operating_removed": 0, "normalized_noi": 1653000 }
  },

  "property": {
    "unit_mix": [
      { "unit_type": "rv_pull_through", "hookup_level": "full", "amp_rating": 50, "count": 96, "occupancy_status": "mixed" },
      { "unit_type": "rv_back_in", "hookup_level": "full", "amp_rating": 30, "count": 54, "occupancy_status": "mixed" },
      { "unit_type": "cabin", "hookup_level": "na", "amp_rating": null, "count": 18 },
      { "unit_type": "tent", "hookup_level": "partial", "amp_rating": null, "count": 14 }
    ],
    "amenities": [
      { "name": "Pool", "category": "recreation", "present": true, "condition": "fair", "notes": "Resurface ~2yr" },
      { "name": "Wi-Fi", "category": "connectivity", "present": true, "condition": "poor" },
      { "name": "Dog park", "category": "recreation", "present": false },
      { "name": "Laundry", "category": "service", "present": true, "condition": "good" }
    ]
  },

  "operations": {
    "bookings": [
      { "booking_id": "bk_…", "site_id": "P-104", "unit_type": "rv_pull_through",
        "check_in": "2024-07-03", "check_out": "2024-07-07", "nights": 4,
        "gross_revenue": 312.00, "adr": 78.00, "channel": "direct",
        "booking_date": "2024-05-20", "lead_time_days": 44 }
    ],
    "weekly_summary": [
      { "week_start": "2024-07-01", "available_unit_nights": 1274, "occupied_unit_nights": 1019,
        "occupancy_pct": 0.80, "adr": 76.40, "revpau": 61.12, "gross_revenue": 77852,
        "source": "computed" }
    ]
  },

  "underwriting": {
    "assumptions": [
      { "key": "stabilized_occupancy", "label": "Stabilized occupancy", "baseline_value": 0.60,
        "shield_source": "portfolio_rv_t12", "override_value": 0.55, "is_overridden": true,
        "overridden_by": "kurtis", "note": "Tougher shoulder season here" },
      { "key": "opex_ratio", "label": "OpEx ratio", "baseline_value": 0.48,
        "shield_source": "portfolio_rv_t12", "is_overridden": false }
    ],
    "hurdles": [
      { "metric": "levered_irr", "default_threshold": 0.15, "deal_threshold": 0.15, "actual": 0.194, "passes": true },
      { "metric": "equity_multiple", "default_threshold": 1.8, "deal_threshold": 1.8, "actual": 2.1, "passes": true },
      { "metric": "going_in_cap", "default_threshold": 0.08, "deal_threshold": 0.08, "actual": 0.116, "passes": true },
      { "metric": "yr1_cash_on_cash", "default_threshold": 0.07, "deal_threshold": 0.07, "actual": 0.069, "passes": false }
    ],
    "waterfall_tiers": [
      { "tier": 1, "irr_floor": 0.00, "irr_ceiling": 0.08, "lp_split": 1.00, "gp_split": 0.00 },
      { "tier": 2, "irr_floor": 0.08, "irr_ceiling": 0.13, "lp_split": 0.80, "gp_split": 0.20 },
      { "tier": 3, "irr_floor": 0.13, "irr_ceiling": null, "lp_split": 0.70, "gp_split": 0.30 }
    ],
    "proforma_results": {
      "years": [ { "yr": 1, "revenue": 3180000, "opex": 1527000, "noi": 1653000,
        "debt_service": 623000, "capex": 91000, "levered_cf": 939000 } ],
      "exit": { "year": 5, "exit_cap": 0.0775, "gross_value": 26770000, "net_proceeds": 16900000 },
      "levered_irr": 0.194, "equity_multiple": 2.1, "equity_basis": 4970000
    }
  },

  "comps": [
    { "comp_id": "cp_…", "name": "Blue Ridge Basecamp", "lat": 35.61, "lng": -82.55,
      "distance_mi": 8.2, "avg_rate": 91.00, "sentiment_score": 4.7,
      "amenity_rank": 1, "amenity_score": 95,
      "ai_summary": "Premium tier — heated pool, pickleball, fiber.",
      "best_snippet": "Best campground we've stayed at", "worst_snippet": "Pricey on weekends",
      "source": "google", "is_manual": false }
  ],

  "gate": {
    "phase": "due_diligence",
    "items": [
      { "question_id": "q_env_phase1", "category": "property", "status": "open", "blocking": true,
        "route_type": "external", "routed_to": "GeoTerra", "date_requested": "2025-05-10",
        "date_received": null, "acceptable": null, "comments": "" },
      { "question_id": "q_rent_roll", "category": "financial", "status": "accepted",
        "blocking": true, "date_received": "2025-05-26", "acceptable": true }
    ],
    "cleared": 21, "total": 24, "ready_to_advance": false
  }
}
```

### 8.4 Database tables (PostgreSQL)

PKs are short prefixed text IDs; timestamps are `timestamptz`. `raw_payload jsonb` on
ingest-fed tables preserves the original parsed file.

```sql
-- ── Core ────────────────────────────────────────────
deals( deal_id PK, name, property_type, address_line1, city, state, zip, lat, lng,
  site_count int, ask_price numeric, price_per_site numeric, seller_name,
  date_received date, current_phase, status, thesis, notes, created_at, updated_at )
deal_photos( photo_id PK, deal_id FK→deals, source, url, caption, review_snippet, sort int )

-- ── Reference / config (not per-deal) ───────────────
gl_accounts( account_code PK, parent_code FK→gl_accounts, level, name, section,
  normal_balance, sort int, active bool )
gl_mappings_learned( mapping_id PK, seller_phrase, source_seller,
  account_code FK→gl_accounts, confirmed_by, confirmed_at, hit_count int )
gate_questions( question_id PK, phase, category, text, blocking bool,
  default_route_type, active bool, created_by, approved_by, created_at )

-- ── Financials ──────────────────────────────────────
financial_periods( period_id PK, deal_id FK→deals, label, period_start date,
  period_end date, granularity )
financial_lines( line_id PK, deal_id FK→deals, period_id FK→financial_periods,
  account_code FK→gl_accounts NULL, account_level, amount numeric, seller_source_line,
  map_confidence, map_confidence_score numeric, noi_placement, is_addback bool,
  addback_amount numeric, reviewed_by, reviewed_at, raw_payload jsonb )

-- ── Property & operations ───────────────────────────
units( unit_id PK, deal_id FK→deals, unit_type, hookup_level, amp_rating int NULL,
  count int, occupancy_status )
amenities( amenity_id PK, deal_id FK→deals, name, category, present bool, condition, notes )
bookings( booking_id PK, deal_id FK→deals, site_id, unit_type, check_in date, check_out date,
  nights int, gross_revenue numeric, adr numeric, channel, booking_date date,
  lead_time_days int, raw_payload jsonb )
weekly_summary( summary_id PK, deal_id FK→deals, week_start date, available_unit_nights int,
  occupied_unit_nights int, occupancy_pct numeric, adr numeric, revpau numeric,
  gross_revenue numeric, source )

-- ── Underwriting ────────────────────────────────────
assumptions( assumption_id PK, deal_id FK→deals, key, label, baseline_value numeric,
  shield_source, override_value numeric NULL, is_overridden bool, overridden_by, note )
hurdles( hurdle_id PK, deal_id FK→deals, metric, default_threshold numeric,
  deal_threshold numeric, actual_value numeric, passes bool )
waterfall_tiers( tier_id PK, deal_id FK→deals, tier int, irr_floor numeric,
  irr_ceiling numeric NULL, lp_split numeric, gp_split numeric )
proforma_results( result_id PK, deal_id FK→deals, yr int, revenue numeric, opex numeric,
  noi numeric, debt_service numeric, capex numeric, levered_cf numeric )
proforma_summary( deal_id PK FK→deals, levered_irr numeric, equity_multiple numeric,
  equity_basis numeric, exit_year int, exit_cap numeric, exit_gross_value numeric,
  exit_net_proceeds numeric )

-- ── Market (population rings) ────────────────────────
population_rings( ring_id PK, deal_id FK→deals, radius_mi int (25|50|100|150),
  baseline_population int NULL, override_population int NULL, is_override bool,
  overridden_by, note, source, as_of date NULL, created_at, updated_at )

-- ── Comps ───────────────────────────────────────────
comps( comp_id PK, deal_id FK→deals, name, lat, lng, distance_mi numeric, avg_rate numeric,
  sentiment_score numeric, amenity_rank int, amenity_score int, ai_summary, best_snippet,
  worst_snippet, source, is_manual bool, scraped_at, raw_payload jsonb )

-- ── Workflow / gates ────────────────────────────────
deal_gate_items( item_id PK, deal_id FK→deals, question_id FK→gate_questions, status,
  blocking bool, route_type, routed_to, date_requested date, date_received date,
  acceptable bool NULL, comments )
question_suggestions( suggestion_id PK, phase, type, text, suggested_by, rationale,
  status, decided_by, decided_at )

-- ── Feedback loop ───────────────────────────────────
feedback_items( feedback_id PK, type, title, description, status, priority, submitted_by,
  role, page_route, deal_id FK→deals NULL, app_version, browser, os, device, viewport,
  console_errors jsonb, breadcrumbs jsonb, last_api_error jsonb, created_at, updated_at )
feedback_attachments( attachment_id PK, feedback_id FK→feedback_items, kind, url )
feedback_comments( comment_id PK, feedback_id FK→feedback_items, author, body, created_at )
feedback_dispatch( dispatch_id PK, feedback_id FK→feedback_items, target, brief,
  github_issue_url, github_pr_url, status, dispatched_by, dispatched_at, updated_at )
```

**Relationship notes.** One `deals` row fans out to all per-deal tables via `deal_id`.
`gl_accounts`, `gate_questions` are shared config edited via admin UI (gate changes go through
`question_suggestions`). `financial_lines.account_code` is nullable so unmapped lines persist.
`bookings` (grain) and `weekly_summary` (rollup) coexist; rollup is recomputed from bookings
when present, else loaded directly.

### 8.5 GL reference — RJourney chart (excerpt; seeds `gl_accounts`)

Four levels; mapping targets the lowest level the source supports. Full chart (~235 lines)
seeds from `RJourneyP_LGLStructure.xlsx`.

| Level | Code | Name |
|---|---|---|
| section | — | Income |
| major_group | 400000 | Revenue |
| subgroup | 400100 | Campground Rent |
| leaf | 400105 | RV Short Term |
| leaf | 400110 | RV Extended Stay |
| leaf | 400115 | Lodging Short Term |
| leaf | 400120 | Tent |
| subgroup | 400200 | Self Storage Rent |
| subgroup | 401000 | Online Travel Agencies |
| subgroup | 402000 | Marina Revenue |
| subgroup | 403000 | Ancillary Revenue |
| subgroup | 404000 | Retail Sales |
| section | — | Expense |
| subgroup | 600200 | Advertising & Promotion |
| subgroup | 605100 | Repairs & Maintenance |
| subgroup | 605400 | Utilities |
| leaf | 605410 | Electric |
| leaf | 605450 | Water-Well Testing & Permits |
| leaf | 605455 | Water & Sewer |
| leaf | 605460 | Septic Pumping & Treatment |
| subgroup | 700000 | Debt Service Interest *(below NOI)* |
| subgroup | 800000 | Non-Operational Expenses *(below NOI)* |

`normal_balance` and `noi_placement` defaults travel with each account, so a `700000` line is
auto-treated as a below-the-line add-back during normalization.

---

## 9. API surface (representative)
```
POST  /auth/callback                 OIDC
GET   /deals                         pipeline list (filter phase/status)
POST  /deals                         create (manual)
GET   /deals/{id}                    full assembled document
PATCH /deals/{id}/phase              advance/kill (gated)
POST  /deals/{id}/documents          upload → queue parse
GET   /deals/{id}/proforma           results
PATCH /deals/{id}/assumptions        override (records author/note)
GET   /deals/{id}/mapping            mapping queue for review
POST  /deals/{id}/mapping/confirm    accept → write learned mapping
GET   /deals/{id}/comps              comp set
POST  /deals/{id}/comps              manual add (url|fields)
GET   /gate-questions?phase=         config
POST  /question-suggestions          suggest
PATCH /question-suggestions/{id}     approve/decline (admin)
POST  /feedback                      widget submit (auto-captures context)
GET   /feedback                      triage queue (filter type/status/priority)
PATCH /feedback/{id}                 status/priority/type/tags
POST  /feedback/{id}/comments        add context / enrichment
POST  /feedback/{id}/attachments     screenshot/file
POST  /feedback/{id}/dispatch        → create GitHub issue w/ @claude brief
POST  /webhooks/email-intake         inbound deal mail
POST  /webhooks/github               sync issue/PR state back to dispatch
```

## 10. Auth & security
- Entra ID OIDC (internal) + secondary external method; RBAC enforced server-side.
- Least-privilege SHIELD read-only credentials; scoped external-partner access per shared deal.
- Secrets in a vault/key service; `ANTHROPIC_API_KEY` for the GitHub Action in repo secrets.
- Branch protection + human PR approval on all Claude-authored changes (§5.12).

## 11. Build phases (and suggested agent-session split)
The data model (§8) is the shared contract, so modules can be built largely in parallel.

- **Phase 0 — Foundation:** repo, Postgres + pgvector, schema migrations, `gl_accounts` + gate-question seeds, auth skeleton, object storage, base logging + Sentry, `CLAUDE.md` standards file. *(do first; everyone depends on it)*
- **Phase 1 — Ingestion & mapping:** Excel/CSV/PDF parsing, GL mapping engine, mapping review UI, NOI bridge.
- **Phase 2 — Underwriting:** SHIELD connector + baseline sync, pro forma engine, waterfall, hurdles, assumption overrides.
- **Phase 3 — Comp intelligence:** discovery, scrapers/API connectors, sentiment + amenity scoring, manual add, visualizations.
- **Phase 4 — Pipeline, gates & feedback:** dashboard, deal-detail tabs, gate logic, suggest→approve, email routing + RMS placeholder, gallery, feedback widget + triage + Claude Code dispatch, full observability dashboards/alerts.

Suggested parallel sessions: (a) ingestion/mapping, (b) SHIELD + pro forma, (c) scrapers/comps,
(d) frontend + gates + feedback — all coding against §8, with Phase 0 landed first.

## 12. Non-functional requirements
- Throughput: comfortably handle 30 new deals/week with parsing + comp scraping.
- Auditability: retain raw payloads and every mapping/override/feedback decision with author + timestamp.
- Resilience: ingest, scraping, and dispatch run as retried background jobs; one bad file never blocks a deal.
- Security: least-privilege credentials; scoped external access; secrets vaulted.
- Observability: §7 telemetry live from Phase 0 onward.

## 13. Assumptions made (verify)
- PostgreSQL/FastAPI/React stack chosen for fit; substitutable if the team has a standard.
- SHIELD is SQL Server, queryable read-only from the app's network.
- Cloud hosting acceptable for deal data (login + RBAC). Confirm data-sensitivity posture.
- Scraping target sites permissible pending ToS/legal review; official APIs preferred where they exist.
- GitHub is the code host and the feedback-dispatch target.

---

## 14. Decisions to resolve

Grouped by owner. **Phase-0 blockers** (answer before build starts): A-defaults are not blocking, but **C-14, C-16, C-17, C-20, B-13, C-28, C-29** are.

### A. Kurtis — business & underwriting
- **A-1.** Default hurdle thresholds (levered IRR, equity multiple, going-in cap, Yr-1 cash-on-cash).
- **A-2.** Waterfall: three hurdle breakpoints, LP/GP split per tier, catch-up?, return-of-capital tier?
- **A-3.** Default LTV, rate basis, amortization vs. IO, target equity split.
- **A-4.** Default hold period and how exit cap is set.
- **A-5.** Mobile pro forma: horizontal scroll vs. condensed card + drill-down.
- **A-6.** Unit mix: per-site rows when a site map exists, or always aggregate to type.
- **A-7.** Financial period grain: T12 + monthly when available?
- **A-8.** Re-master the DD checklist for RV (utilities/electrical incl. 50-amp, water source & rights, septic capacity, detailed unit mix, booking-system data, amenity equipment, franchise/membership transfer, insurance loss runs, flood zone, zoning/density, ADA). Confirm full 50+ and which are blocking.
- **A-9.** Seed Initial UW (P&L + unit mix) and LOI (attorneys looped, deal points) gate sets.
- **A-10.** Failed-deal retention before archive; "circle back" trigger.
- **A-33.** Who, besides you, can triage and dispatch feedback; turnaround targets (bug vs. feature).
- **A-34.** Notify the original submitter when their item ships?

### B. CFO (Kurt Ross) & finance
- **B-11.** Exact above/below-the-line NOI definition (CapEx allocation, mgmt fee, reserves).
- **B-12.** Standard auto add-backs (owner debt service, personal auto, owner comp, one-time items).
- **B-13.** Confirm `RJourneyP_LGLStructure.xlsx` is the current, complete chart and who owns changes. *(Phase-0)*

### C. CTO (James Snook) & IT (Sean Michael) — integrations & infra
- **C-14.** SHIELD read-only connection details, network reachability, relevant tables/views. *(Phase-0)*
- **C-15.** Which SHIELD baseline metrics to pull and at what grain.
- **C-16.** Confirm Entra ID for internal SSO + external method (magic-link vs. password). *(Phase-0)*
- **C-17.** Cloud provider/region; any environment constraint on deal data. *(Phase-0)*
- **C-18.** Deal intake email address and read mechanism (Graph vs. inbound-parse).
- **C-19.** RMS ticketing: confirm placeholder now; obtain eventual API contract.
- **C-20.** Approve Claude + embeddings provider; key ownership + budget. *(Phase-0)*
- **C-21.** Secrets management location.
- **C-28.** GitHub org/repo, branch-protection rules, write-enabled `@claude` now vs. review-first. *(Phase-0)*
- **C-29.** `ANTHROPIC_API_KEY` ownership for the Action + monthly spend cap. *(Phase-0)*
- **C-30.** Error-tracking provider (Sentry?) + data-residency.
- **C-31.** Alert channel (Slack / email / PagerDuty).

### D. Legal / compliance
- **D-22.** Scraping ToS review (Google, TripAdvisor, Yelp, Campendium/Camp Media, The Dirt); official APIs + budget where available.
- **D-23.** Rights to display website/Google customer photos in the gallery.
- **D-24.** What deal data PE partners may see; NDA/confidentiality gating per deal.
- **D-32.** Screenshot/PII policy: bug screenshots may contain deal financials — capture, redaction, retention, viewers.

### E. Scope & sequencing
- **E-25.** Confirm Phase 0→1→2 as first usable release; comps and full gate/feedback follow.
- **E-26.** Parallel vs. sequential module build (parallel needs Phase 0 landed + contract frozen).
- **E-27.** Post-build ownership: deployments, gate-question config, GL chart updates.

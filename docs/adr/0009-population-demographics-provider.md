# 0009. Population / demographics provider for market rings

Date: 2026-06-11
Status: Proposed

## Context

The Initial UW market view needs **population rings** — estimated population within
25/50/100/150 miles of a deal — auto-pulled when a property is entered. This requires a
demographics data source (e.g. US Census ACS, Esri, or a radius-demographics API). Picking
the provider + key ownership + budget is a new decision (not in the original §14 list).

## Decision

**Unresolved — pending CTO/Operations.** The engine ships a provider seam
(`population.provider.PopulationProvider`) whose factory `build_population_provider()`
returns None until `POPULATION_PROVIDER` + `POPULATION_PROVIDER_API_KEY` are configured. Per
CLAUDE.md, no population figures are fabricated: with no provider, rings stay empty and the
underwriter enters/overrides them manually (baseline + override + author + note retained).
The `population_rings` table (§8) and the auto-pull-on-create flow are in place now; wiring a
concrete provider's HTTP client is a small follow-up once this decision lands.

## Consequences

- Population rings work end-to-end via manual entry today; auto-pull activates the moment a
  provider is configured (no schema/contract change needed).
- The estimate vintage (`as_of`) and `source` travel with each ring for provenance.
- Provider choice affects radius-band methodology and cost; record the accepted provider,
  key owner, and any per-call budget here when decided.

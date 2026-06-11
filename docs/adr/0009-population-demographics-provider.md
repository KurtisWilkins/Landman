# 0009. Population / demographics provider for market rings

Date: 2026-06-11
Status: Accepted

## Context

The Initial UW market view needs **population rings** — estimated population within
25/50/100/150 miles of a deal — auto-pulled when a property is entered. This requires a
demographics data source (e.g. US Census ACS, Esri, or a radius-demographics API). Picking
the provider + key ownership + budget is a new decision (not in the original §14 list).

## Decision

**US Census ACS 5-year (county grain).** The wired provider
(`population.census.CensusACSProvider`) estimates each ring by summing ACS 5-year total
population (table `B01003`) for every county whose **internal-point centroid** falls within
the ring radius of the deal. County centroids are bundled from the US Census 2023 Gazetteer
(`population/data/us_county_centroids.csv`, ~3,200 rows); population is pulled live from the
free Census Data API in one nationwide call per refresh.

- Activated by config: `POPULATION_PROVIDER=census` + `POPULATION_PROVIDER_API_KEY` (a free
  Census key — gates rate limits, not access). Vintage via `CENSUS_ACS_YEAR` (default 2022).
- The factory still returns `None` when unconfigured, so populations are never fabricated;
  with no provider, rings stay operator-entered (baseline + override + author + note).
- No PII: only aggregate population is requested. Cost: **free** (public API).

## Consequences

- Population rings auto-pull the moment the key is configured; manual override is unchanged.
- The estimate vintage (`as_of` = ACS end-year) and `source` (`census_acs`) travel with each
  ring for provenance.
- **County grain is coarse**, especially for the 25-mile ring. A ring that captures *no*
  county centroid is **omitted** (left unestimated) rather than reported as a misleading
  zero — the underwriter then enters/overrides it. Rings are naturally cumulative (a larger
  radius includes every county of the smaller ones).
- A future refinement could swap the bundled centroid dataset to **census-tract** grain (more
  accurate inner rings) with no schema or API-contract change — only the provider's data file
  and per-state fetch logic would change.
- Key ownership: a free Census API key to be provisioned by Operations and stored as a secret
  (never committed). Budget: none.

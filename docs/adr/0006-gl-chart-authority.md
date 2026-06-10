# 0006. GL chart authority and completeness (B-13)

Date: 2026-06-10
Status: Proposed

## Context

§14 **B-13** (Phase-0 blocker): confirm `RJourneyP_LGLStructure.xlsx` is the current,
complete chart of accounts (~235 lines) and name who owns changes. §8.5 publishes only an
excerpt; the mapping engine (§5.3) targets the lowest justifiable level against this chart.

## Decision

**Unresolved — pending CFO (Kurt Ross).** Phase 0 seeds `gl_accounts` from the §8.5
**excerpt** only (20 rows, hierarchy + `default_noi_placement` so 700000→below and
800000→non-operating). The full chart loads from `GL_CHART_CONFIG_PATH` once the file is
confirmed; the seed loader has a merge hook with `TODO(decision: §14 B-13)`. No accounts
are invented.

## Consequences

- Mapping in Phase 1 works against the excerpt now and the full chart once supplied.
- Re-seeding with the full chart is additive (upsert by `account_code`); ownership of
  ongoing chart changes must be named (relates to E-27).

# 0005. AI + embeddings provider and key ownership (C-20)

Date: 2026-06-10
Status: Proposed

## Context

§14 **C-20** (Phase-0 blocker): approve the Claude + embeddings provider, key ownership,
and budget. The design doc defaults to Anthropic Claude (extraction, GL classification,
comp/narrative) and Voyage embeddings (GL mapping shortlist via pgvector). CLAUDE.md sets
`claude-sonnet-4-6` as the default model, escalating to opus only for complex reasoning.

## Decision

**Unresolved (provider defaults proposed) — pending CTO.** Phase 0 reserves the pgvector
`embedding` column (dim configurable) and reads `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`,
and `VOYAGE_API_KEY` from config with `TODO(decision: §14 C-20)`. No AI/embedding call is
made in Phase 0; the embedding dimension is finalized when the model is confirmed.

## Consequences

- Phase 1 (mapping) and Phase 3 (comps) depend on this key/provider decision.
- The same `ANTHROPIC_API_KEY` powers the GitHub Action (C-29) — track spend caps there.
- Changing embedding model/dimension later requires re-embedding `gl_accounts`.

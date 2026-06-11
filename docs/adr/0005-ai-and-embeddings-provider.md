# 0005. AI + embeddings provider and key ownership (C-20)

Date: 2026-06-10
Status: Accepted (resolved 2026-06-11)

## Context

§14 **C-20** (Phase-0 blocker): approve the Claude + embeddings provider, key ownership,
and budget. The design doc defaults to Anthropic Claude (extraction, GL classification,
comp/narrative) and Voyage embeddings (GL mapping shortlist via pgvector). CLAUDE.md sets
`claude-sonnet-4-6` as the default model, escalating to opus only for complex reasoning.

## Decision

**Resolved 2026-06-11: Anthropic Claude + Voyage.** Claude handles extraction, GL
classification, comp sentiment/amenity summaries, and first-pass narrative
(`claude-sonnet-4-6` default; opus only for genuinely complex reasoning). **Voyage**
provides the embeddings for the GL-mapping shortlist (pgvector). `ANTHROPIC_API_KEY` is set
(ADR-0008); the pgvector `embedding` dimension follows the selected Voyage model — confirm
the model before embedding `gl_accounts`, since changing it later requires re-embedding.

_Original Phase-0 analysis:_ Phase 0 reserves the pgvector
`embedding` column (dim configurable) and reads `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`,
and `VOYAGE_API_KEY` from config with `TODO(decision: §14 C-20)`. No AI/embedding call is
made in Phase 0; the embedding dimension is finalized when the model is confirmed.

## Consequences

- Phase 1 (mapping) and Phase 3 (comps) depend on this key/provider decision.
- The same `ANTHROPIC_API_KEY` powers the GitHub Action (C-29) — track spend caps there.
- Changing embedding model/dimension later requires re-embedding `gl_accounts`.

# 0001. Record architecture decisions

Date: 2026-06-10
Status: Accepted

## Context

The platform has many open `[DECISION]` items (design doc §14) and a stack chosen for fit
rather than mandate. We need a lightweight, durable way to capture decisions and their
trade-offs so future contributors (human and Claude Code) understand *why*, not just *what*.

## Decision

Use Architecture Decision Records. Each material decision gets a numbered Markdown file in
`docs/adr/NNNN-title.md` using the template in `CONTRIBUTING.md`. Resolving a design-doc
`[DECISION]` requires an ADR, linked from the implementing PR. The design doc remains the
living spec; ADRs are the dated decision trail behind it.

## Consequences

- Decisions are discoverable and reversible with context; superseding is explicit.
- Small ongoing overhead per decision — accepted as cheaper than re-litigating choices.
- The first real ADRs should resolve the Phase-0 blockers (SHIELD access, identity provider,
  hosting, AI provider/keys, GL-chart authority, GitHub repo + API-key spend) before build starts.

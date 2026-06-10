# 0008. ANTHROPIC_API_KEY ownership + spend cap (C-29)

Date: 2026-06-10
Status: Proposed

## Context

§14 **C-29** (Phase-0 blocker): name the owner of the `ANTHROPIC_API_KEY` used by the
GitHub Action and set a monthly spend cap. §5.12 stores the key in repo secrets only.

## Decision

**Unresolved — pending CTO.** The workflows reference `secrets.ANTHROPIC_API_KEY`; the key
is never committed and lives only in repository secrets. Ownership and the spend cap are
recorded here once set; `.env.example` notes the same key is also set as a repo secret with
`TODO(decision: §14 C-29)`.

## Consequences

- Until the secret is set, the Action cannot run; CI (lint+test) is unaffected.
- Spend monitoring/cap and key rotation ownership must be assigned before enabling
  write-enabled `@claude` at scale (relates to C-28, C-20).

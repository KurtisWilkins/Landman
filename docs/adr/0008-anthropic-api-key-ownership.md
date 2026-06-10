# 0008. ANTHROPIC_API_KEY ownership + spend cap (C-29)

Date: 2026-06-10
Status: Accepted (spend cap is a placeholder — confirm final amount)

## Context

§14 **C-29** (Phase-0 blocker): name the owner of the `ANTHROPIC_API_KEY` used by the
GitHub Action and set a monthly spend cap. §5.12 stores the key in repo secrets only.

## Decision

- **Key:** set as the `ANTHROPIC_API_KEY` repository secret (Settings → Secrets and
  variables → Actions). Never committed; the workflows reference `secrets.ANTHROPIC_API_KEY`
  only. A previously-exposed key was revoked and rotated.
- **Owner:** Kurtis Wilkins (President of Operations) owns the key and its rotation.
- **Monthly spend cap:** **$20/month — placeholder.** Set as a usage limit in the Anthropic
  Console. `TODO(decision: §14 C-29)`: confirm the real cap before enabling write-enabled
  `@claude` at scale or running the dispatch loop on real volume.

## Consequences

- The `@claude` Action and the automated PR-review workflow can now run; CI (lint+test)
  remains independent of the key.
- The $20 placeholder is low enough to fail safe (the Action stops rather than overspends)
  but will throttle heavy use — revisit alongside C-28 (write-enabled posture) and C-20
  (AI provider budget).
- Key rotation ownership is assigned; rotate on any suspected exposure.


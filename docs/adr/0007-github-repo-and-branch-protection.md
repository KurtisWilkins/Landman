# 0007. GitHub repo, branch protection, and @claude posture (C-28)

Date: 2026-06-10
Status: Accepted (resolved 2026-06-11)

## Context

§14 **C-28** (Phase-0 blocker): confirm the GitHub org/repo, branch-protection rules, and
whether write-enabled `@claude` runs now vs. review-first. §5.12 mandates review-first, no
auto-merge, and least-privilege workflow permissions.

## Decision

**Resolved 2026-06-11: review-first, kept.** Repo is **`KurtisWilkins/Landman`**. `@claude`
opens PRs for human review with **no auto-merge**; branch protection on `main` requires human
approval + green CI (`ci.yml` lint+test). Workflow permissions stay least-privilege
(`contents`/`pull-requests`/`issues`/`id-token`). **Write-enabled expansion is deferred**
until path filters and trigger rules are defined.

_Original Phase-0 analysis:_ Phase 0 ships
`.github/workflows/claude.yml` (responds only to explicit `@claude` mentions) and
`claude-code-review.yml` (automated first-pass review, no merge), both scoped to
`contents`/`pull-requests`/`issues`/`id-token`. CI (`ci.yml`) runs lint+test. Branch
protection requiring human approval + green CI must be enabled on `main` (CONTRIBUTING.md);
`GITHUB_REPO` is a config placeholder with `TODO(decision: §14 C-28)`.

## Consequences

- No Claude-authored change can merge without human approval and green CI.
- Write-enabled automation expands only after protection, path filters, and trigger rules
  are set. The actual org/repo and protection config are recorded here once applied.

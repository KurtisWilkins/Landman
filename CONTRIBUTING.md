# Contributing

Applies to humans and to Claude Code (interactive or via the GitHub Action). Read `CLAUDE.md`
first — it holds the coding standards; this file holds the workflow.

## Branching

- Branch from `main`: `feat/<short-name>`, `fix/<short-name>`, `chore/<short-name>`.
- One issue per branch where possible. Keep branches short-lived.
- `main` is protected: no direct pushes, required PR review, required green CI.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/):
`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `perf:`. Imperative mood, present
tense. Reference the issue (`fix: correct NOI add-back exclusion (#42)`).

## Pull requests

- Fill in the PR template. Link the issue it resolves.
- One concern per PR. If it grows beyond a reviewable size, split it.
- Must pass `make lint` and `make test` locally before opening.
- Update `docs/` and add an ADR (below) when you change behavior, architecture, or resolve a `[DECISION]`.
- **No self-merge of significant changes and no auto-merge.** A human reviews and merges every PR — especially Claude-authored ones.

## The `@claude` workflow

When an issue or PR comment mentions `@claude`, the GitHub Action
(`.github/workflows/claude.yml`) runs Claude Code, which implements on a branch and opens a PR.

- Treat Claude's PRs like any contributor's: review the diff, run it, request changes.
- To refine, comment again with more context and re-mention `@claude`. Provide repro steps, the desired behavior, and affected files — richer context yields better PRs.
- Claude follows `CLAUDE.md`; if it goes off-pattern, fix `CLAUDE.md` rather than re-explaining each time.
- A separate workflow (`.github/workflows/claude-code-review.yml`) posts an automated first-pass review on every PR. It does not replace human review.

### Review-first posture

Start the Action read/review-only and expand to write-enabled automation only after branch
protection, path filters, and trigger rules are set (design doc §5.12). Workflow permissions
stay limited to `contents`, `pull-requests`, `issues`, `id-token`. The API key lives only in
repository secrets.

## Architecture Decision Records (ADRs)

Material decisions get a short ADR in `docs/adr/NNNN-title.md`. This is where the design doc's
`[DECISION]` items get resolved and recorded.

```markdown
# NNNN. <Title>
Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by NNNN

## Context
What's the situation and the forces at play?

## Decision
What we chose, stated plainly.

## Consequences
Trade-offs, follow-ups, and what this rules out.
```

Number sequentially. Link the ADR from the PR that implements it.

## Definition of done

Code + tests, green `lint`/`test`, docs/ADR updated if needed, PR linked to its issue,
`CLAUDE.md` rules honored (provenance, no guessed `[DECISION]` values, human-in-the-loop), and
a human approval recorded.

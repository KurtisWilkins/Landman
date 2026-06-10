<!-- Keep PRs focused: one concern. Link the issue this resolves. -->

## What & why
<!-- What changed and the reason. Link the issue: Closes #___ -->

## Type
- [ ] feat
- [ ] fix
- [ ] refactor
- [ ] docs
- [ ] chore / test

## Checklist
- [ ] `make lint` and `make test` pass locally
- [ ] New logic has tests; a bug fix has a regression test that failed before the fix
- [ ] No hard-coded `[DECISION]` value or business threshold (reads from config + `TODO(decision)`)
- [ ] Schema changes match design doc §8 and include an Alembic migration
- [ ] Provenance preserved (financial-line source/confidence/NOI placement; assumption baseline/override)
- [ ] No secrets or PII committed or logged; SHIELD untouched (read-only)
- [ ] Docs / ADR updated if behavior, architecture, or a `[DECISION]` changed

## Screenshots / notes
<!-- UI changes: before/after, mobile + desktop. Anything reviewers should focus on. -->

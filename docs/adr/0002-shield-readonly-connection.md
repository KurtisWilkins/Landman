# 0002. SHIELD read-only connection (C-14)

Date: 2026-06-10
Status: Proposed

## Context

Design-doc §14 **C-14** (a Phase-0 blocker) requires SHIELD (the existing SQL Server
operations DB) read-only connection details, network reachability, and the relevant
tables/views. Phase 2 (SHIELD connector + baseline sync, §5.4) depends on this. Per
CLAUDE.md, SHIELD access is **read-only** and the app must never attempt a write.

## Decision

**Unresolved — pending Kurtis/CTO (James Snook) / IT (Sean Michael).** Phase 0 does not
hard-code any value. The connection is scaffolded behind named env placeholders
(`SHIELD_HOST/PORT/DB/READONLY_USER/READONLY_PASSWORD` in `.env.example` and
`core/config.py`) with `TODO(decision: §14 C-14)`. No SHIELD driver/connection is opened
until these are supplied; the connector and its schema-drift snapshot land in Phase 2.

## Consequences

- Phase 0 ships without a live SHIELD dependency; Phase 2 is blocked until C-14 (and the
  metric set C-15) are answered.
- Credentials must be least-privilege read-only and vaulted (C-21); never committed.
- Supersede this ADR with the accepted connection contract before Phase 2 begins.

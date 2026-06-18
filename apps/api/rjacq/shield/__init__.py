"""SHIELD integration (design doc §5.4): a **read-only** connection to RJourney's existing
operations DB (SQL Server). A scheduled job pulls portfolio actuals, aggregates baseline
metrics, and seeds each acquisition's assumptions; a schema snapshot flags drift.

Hard rule (CLAUDE.md / §10): SHIELD access is least-privilege read-only — the app must never
write to SHIELD. Connection details and the metric set are unresolved decisions (§14 C-14 /
C-15) and are read from config; nothing is hard-coded or guessed.
"""

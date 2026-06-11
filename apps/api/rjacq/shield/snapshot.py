"""SHIELD schema-snapshot drift detection (design doc §5.4).

Keep a snapshot of SHIELD's schema so the connector flags drift if SHIELD changes (a moved
or dropped column would silently break baseline aggregation). Pure + tested.
"""

from __future__ import annotations

Snapshot = dict[str, list[str]]  # table -> column names


def detect_drift(stored: Snapshot, current: Snapshot) -> list[str]:
    """Human-readable drift between a stored snapshot and the current schema."""
    changes: list[str] = []
    for table in sorted(set(stored) - set(current)):
        changes.append(f"table removed: {table}")
    for table in sorted(set(current) - set(stored)):
        changes.append(f"table added: {table}")
    for table in sorted(set(stored) & set(current)):
        before, after = set(stored[table]), set(current[table])
        for col in sorted(before - after):
            changes.append(f"column removed: {table}.{col}")
        for col in sorted(after - before):
            changes.append(f"column added: {table}.{col}")
    return changes

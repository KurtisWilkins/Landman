"""Sheet/file-type detection from header heuristics (design doc §5.2).

A coarse classifier is enough to route to the right normalizer; ambiguous sheets fall back
to a Claude classification pass (gated on C-20) in the service.
"""

from __future__ import annotations

from collections.abc import Sequence

SheetType = str  # 'pnl' | 'unit_mix' | 'rent_roll' | 'booking' | 'unknown'

_HINTS: dict[str, tuple[set[str], set[str]]] = {
    # Each entry maps a sheet type to (group A, group B); a header must hit both groups.
    "booking": (
        {"check_in", "checkin", "arrival", "check in"},
        {"check_out", "checkout", "departure", "nights", "check out"},
    ),
    "rent_roll": ({"site", "space", "lot", "unit"}, {"tenant", "occupant", "rent", "lease"}),
    "unit_mix": (
        {"unit_type", "site type", "type", "unit"},
        {"count", "sites", "qty", "quantity", "spaces"},
    ),
    "pnl": (
        {"account", "description", "line item", "gl", "category"},
        {"amount", "total", "balance", "actual", "ytd"},
    ),
}


def _hits(headers: Sequence[str], hints: set[str]) -> bool:
    """True if any header contains any hint (substring, case-insensitive)."""
    lowered = [h.strip().lower() for h in headers if h]
    return any(hint in h for h in lowered for hint in hints)


def detect_sheet_type(headers: Sequence[str]) -> SheetType:
    """Classify a sheet by its header row. Order matters: most specific first."""
    for sheet_type, (group_a, group_b) in _HINTS.items():
        if _hits(headers, group_a) and _hits(headers, group_b):
            return sheet_type
    return "unknown"

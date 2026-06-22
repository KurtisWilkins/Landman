"""Pure budget math (design doc §5.5).

Prior-year monthly actuals are computed on read from a mapped line's ``raw_payload`` (the
QuickBooks recap parser stores each month there); nothing is stored for prior year. Decimal
throughout, no DB/IO, so this is unit-tested like the pro-forma and waterfall engines.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..ingestion.records import to_decimal

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def month_index_of(header: str) -> int | None:
    """Calendar month (1-12) for a recap month-column header like 'JUN 25' / 'January 2026'.
    None for non-month keys (the '_seller_line' / '_section' provenance keys, or any key without a
    year), so 'this June' aligns to 'last June' regardless of fiscal start."""
    key = header.strip().lower()
    if not key or key.startswith("_"):
        return None
    if key[:3] in _MONTHS and any(c.isdigit() for c in key):  # require a year to avoid false hits
        return _MONTHS[key[:3]]
    return None


def bucket_line_months(raw_payload: dict[str, Any]) -> dict[int, Decimal]:
    """Sum a mapped line's per-month raw values into calendar-month buckets (1-12)."""
    out: dict[int, Decimal] = {}
    for key, value in raw_payload.items():
        idx = month_index_of(key)
        if idx is None:
            continue
        amount = to_decimal(str(value))
        if amount is None:
            continue
        out[idx] = out.get(idx, Decimal(0)) + amount
    return out


def variance(prior: Decimal, current: Decimal) -> tuple[Decimal, Decimal | None]:
    """($, %) variance of year-one vs prior. The % is None when prior is 0 (new line / n/a)."""
    abs_var = current - prior
    pct_var = (abs_var / prior) if prior != 0 else None
    return abs_var, pct_var

"""Pure budget math (design doc §5.5).

Prior-year monthly actuals are computed on read from a mapped line's ``raw_payload`` (the
QuickBooks recap parser stores each month there); nothing is stored for prior year. Decimal
throughout, no DB/IO, so this is unit-tested like the pro-forma and waterfall engines.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..ingestion.records import to_decimal

_ZERO = Decimal(0)

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


# ── Two-column grid roll-up (§5.5) ──────────────────────────────────────────
# The only outputs that matter per underwriting: TOTAL REVENUE and TOTAL EXPENSES → NOI, for
# both the prior-year and year-one columns. Pure + Decimal so it's unit-tested with worked
# examples and the year-one NOI here matches the downstream stabilized NOI bridge (same
# above-the-line rule: only ``placement == "above"`` counts; below-the-line / non-operating are
# excluded). A row removed from the year-one projection simply passes ``year1 = 0`` (its prior
# stays as reference).


@dataclass(frozen=True)
class GridLine:
    """One grid line for the roll-up: its NOI placement, whether it's an expense, and the prior
    + year-one amounts (already resolved to overrides-or-defaults by the caller)."""

    placement: str  # "above" | "below" | "non_operating"
    is_expense: bool
    prior: Decimal
    year1: Decimal


@dataclass(frozen=True)
class GridTotals:
    prior_revenue: Decimal
    year1_revenue: Decimal
    prior_expense: Decimal
    year1_expense: Decimal
    prior_noi: Decimal
    year1_noi: Decimal


def roll_up(lines: Sequence[GridLine]) -> GridTotals:
    """Sum revenue/expense for both columns and derive NOI = revenue − expense. Only
    above-the-line lines count toward NOI (matches ``engine.normalized_noi``)."""
    pr = yr = pe = ye = _ZERO
    for ln in lines:
        if ln.placement != "above":
            continue  # below-the-line + non-operating are excluded from operating NOI
        if ln.is_expense:
            pe += ln.prior
            ye += ln.year1
        else:
            pr += ln.prior
            yr += ln.year1
    return GridTotals(
        prior_revenue=pr,
        year1_revenue=yr,
        prior_expense=pe,
        year1_expense=ye,
        prior_noi=pr - pe,
        year1_noi=yr - ye,
    )

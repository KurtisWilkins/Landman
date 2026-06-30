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


# ── Hierarchical roll-up (canonical GL tree: section → group → sub-group → detail) ───────────
# Mirrors the source income statement's nested "Total - …" structure: every group/sub-group total
# is the sum of its descendant leaves, for both the prior and year-one columns. Contra lines (e.g.
# Utility Recovery, Discounts) carry their NATIVE NEGATIVE sign, so summing nets them against their
# siblings automatically — no special-casing. NOI = Total Income − Total Expense uses the same
# above-the-line rule as ``roll_up`` (COGS folds into Expense; below-the-line / non-operating are
# excluded). Pure + Decimal so it's unit-tested against the workbook's own group/section totals.


@dataclass(frozen=True)
class TreeNode:
    """One chart node for the roll-up: its code, parent (None at the section root), the section it
    belongs to (Income | Expense | other), and its NOI placement."""

    code: str
    parent_code: str | None
    section: str | None
    placement: str  # "above" | "below" | "non_operating"


@dataclass(frozen=True)
class TreeRollup:
    # Per-node (prior, year1) subtotal for EVERY node — leaves pass through, groups sum descendants.
    subtotals: dict[str, tuple[Decimal, Decimal]]
    prior_revenue: Decimal
    year1_revenue: Decimal
    prior_expense: Decimal
    year1_expense: Decimal
    prior_noi: Decimal
    year1_noi: Decimal


def roll_up_tree(
    nodes: Sequence[TreeNode], amounts: dict[str, tuple[Decimal, Decimal]]
) -> TreeRollup:
    """Roll leaf ``amounts`` (code → (prior, year1)) up the parent chain to every ancestor, and
    derive section totals + NOI. ``amounts`` are keyed on leaf codes; each value is added to the
    leaf and each of its ancestors (sign preserved, so contra lines net within their parent)."""
    parent = {n.code: n.parent_code for n in nodes}
    section = {n.code: n.section for n in nodes}
    placement = {n.code: n.placement for n in nodes}
    sub: dict[str, list[Decimal]] = {n.code: [_ZERO, _ZERO] for n in nodes}
    pr = yr = pe = ye = _ZERO
    for code, (p, y) in amounts.items():
        cur: str | None = code
        seen: set[str] = set()
        while cur is not None and cur in sub and cur not in seen:
            seen.add(cur)
            sub[cur][0] += p
            sub[cur][1] += y
            cur = parent.get(cur)
        if placement.get(code, "above") == "above":
            sec = section.get(code)
            if sec == "Income":
                pr += p
                yr += y
            elif sec == "Expense":
                pe += p
                ye += y
    return TreeRollup(
        subtotals={c: (v[0], v[1]) for c, v in sub.items()},
        prior_revenue=pr,
        year1_revenue=yr,
        prior_expense=pe,
        year1_expense=ye,
        prior_noi=pr - pe,
        year1_noi=yr - ye,
    )

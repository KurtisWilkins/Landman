"""Pure labor-plan math (design doc §5.5). Decimal only — never float for money/hours/rates.

A deal's labor plan is a list of positions; this turns it into the dollar amounts that feed the
budget's Wages cluster and (for work campers) the revenue/discount lines. Flat-lined: a position
works a constant ``hours_per_week`` between its start and end (``active_weeks``). A WORK CAMPER
draws no cash wage — its comp is the campsite, modeled as extended-stay revenue offset by a
work-camper campsite credit (contra-revenue), per the underwriting convention. Pure + unit-tested
like the pro-forma / promote / budget engines; nothing here decides a business number (rates and
loads are passed in by the caller from per-deal data + config).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal(0)
WEEKS_PER_YEAR = Decimal(52)
MONTHS_PER_YEAR = Decimal(12)


def total_headcount(counts: Sequence[int | None]) -> int:
    """Authoritative roster headcount = sum of per-role counts (a missing count counts as 1).
    The Labor roster is the single source of truth the whole app reads (the Operating-tab display
    and the per-employee payroll-budget default); headcount is never stored a second time."""
    return sum((c or 1) for c in counts)


_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("general_manager", ("general manager", "gm", "manager", "owner")),
    ("front_desk", ("front desk", "reception", "office", "guest service", "clerk", "host")),
    ("housekeeper", ("housekeep", "cleaning", "janitor", "custodial", "laundry")),
    ("maintenance", ("maintenance", "grounds", "groundskeep", "facilities", "repair", "landscap")),
    ("events_coordinator", ("event", "activit", "recreation")),
)


def normalize_role(text: str) -> str:
    """Map a free-text OM role/title onto our role vocabulary; unknown titles become 'custom'
    (the caller keeps the original text as the label)."""
    t = text.strip().lower()
    for role, keys in _ROLE_KEYWORDS:
        if any(k in t for k in keys):
            return role
    return "custom"


def active_weeks(start: date | None, end: date | None) -> Decimal:
    """Flat-lined weeks a position is active between start and end (0 if missing/invalid)."""
    if start is None or end is None:
        return ZERO
    days = Decimal((end - start).days)
    if days <= 0:
        return ZERO
    return days / Decimal(7)


@dataclass(frozen=True)
class LaborPosition:
    """One planned position, resolved to the numbers the cost roll-up needs."""

    headcount: int
    hours_per_week: Decimal
    hourly_rate: Decimal
    weeks: Decimal  # active weeks (caller computes from start/end via active_weeks)
    benefits_eligible: bool
    is_work_camper: bool
    site_weekly_rate: Decimal  # work camper only: extended-stay revenue per week
    campsite_credit_weekly: Decimal  # work camper only: comp booked as a discount/allowance


@dataclass(frozen=True)
class LaborContext:
    """Config loads (None = not configured → that component contributes nothing)."""

    benefits_monthly_per_employee: Decimal | None  # flat $/eligible employee/month → GL 600130
    payroll_tax_pct: Decimal | None  # fraction of cash wages → GL 600155


@dataclass(frozen=True)
class LaborTotals:
    wages: Decimal  # → 600140 Payroll Expenses
    benefits: Decimal  # → 600130 Employee Health Benefits
    payroll_tax: Decimal  # → 600155 Payroll Tax Expense
    extended_stay_revenue: Decimal  # → 400110 RV Extended Stay (work campers)
    work_camper_credit: Decimal  # → 421300 Work Camper Campsite Credit (contra-revenue)
    total_cash_labor: Decimal  # wages + benefits + payroll_tax (the expense the budget sees)


def position_wages(p: LaborPosition) -> Decimal:
    """Cash wages. A work camper draws none — comp is the campsite (see revenue/credit)."""
    if p.is_work_camper:
        return ZERO
    return p.hours_per_week * p.hourly_rate * p.weeks * Decimal(p.headcount)


def position_benefits(p: LaborPosition, ctx: LaborContext) -> Decimal:
    """Flat $/eligible employee/month, pro-rated by active weeks. None unless benefit-eligible,
    not a work camper, and the monthly figure is configured."""
    if p.is_work_camper or not p.benefits_eligible or ctx.benefits_monthly_per_employee is None:
        return ZERO
    active_months = p.weeks * MONTHS_PER_YEAR / WEEKS_PER_YEAR
    return ctx.benefits_monthly_per_employee * active_months * Decimal(p.headcount)


def roll_up(positions: list[LaborPosition], ctx: LaborContext) -> LaborTotals:
    """Sum the plan into the GL amounts. Payroll tax is a config % of cash wages."""
    wages = sum((position_wages(p) for p in positions), ZERO)
    benefits = sum((position_benefits(p, ctx) for p in positions), ZERO)
    payroll_tax = wages * ctx.payroll_tax_pct if ctx.payroll_tax_pct is not None else ZERO
    ext = sum(
        (
            p.site_weekly_rate * p.weeks * Decimal(p.headcount)
            for p in positions
            if p.is_work_camper
        ),
        ZERO,
    )
    credit = sum(
        (
            p.campsite_credit_weekly * p.weeks * Decimal(p.headcount)
            for p in positions
            if p.is_work_camper
        ),
        ZERO,
    )
    return LaborTotals(
        wages=wages,
        benefits=benefits,
        payroll_tax=payroll_tax,
        extended_stay_revenue=ext,
        work_camper_credit=credit,
        total_cash_labor=wages + benefits + payroll_tax,
    )

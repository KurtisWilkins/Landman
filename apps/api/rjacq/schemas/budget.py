"""Year-one budget schemas (design doc §5.5, §9)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class BudgetRow(BaseModel):
    """One canonical GL: prior-year actuals (read-only, computed) beside the editable year-one
    projection, month by month, with variance and provenance."""

    account_code: str
    name: str
    section: str | None = None
    source: str  # actuals | default | placeholder | mixed
    prior_months: list[Decimal | None] = Field(default_factory=list)  # 12 calendar months
    year1_months: list[Decimal | None] = Field(default_factory=list)  # 12 calendar months
    prior_annual: Decimal
    year1_annual: Decimal
    var_abs: Decimal
    var_pct: Decimal | None = None
    is_overridden: bool = False
    note: str | None = None


class BudgetTotals(BaseModel):
    prior_revenue: Decimal
    year1_revenue: Decimal
    prior_opex: Decimal
    year1_opex: Decimal
    prior_noi: Decimal
    year1_noi: Decimal


class BudgetDoc(BaseModel):
    status: str  # draft | locked
    rows: list[BudgetRow] = Field(default_factory=list)
    totals: BudgetTotals
    placeholder_count: int = 0  # unresolved "to review" lines (block the lock)
    unmapped_count: int = 0  # seller lines still unmapped (block the lock)


class BudgetCellUpdate(BaseModel):
    """PATCH /acquisitions/{id}/budget — edit one year-one cell (flips it to an override)."""

    account_code: str
    month_index: int
    year1_amount: Decimal | None = None
    note: str | None = None

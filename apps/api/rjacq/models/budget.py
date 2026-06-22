"""Year-one underwriting budget (design doc §5.5).

The budget is laid out like a budget: each canonical GL's prior-year actuals (computed on read
from the mapped financial lines' ``raw_payload``) beside the editable year-one projection. Only
the editable year-one cells are stored here — one row per (acquisition, account, month). Prior
year, variance, and subtotals are derived. The budget rolls up to the canonical store's
stabilized NOI; it never duplicates shared inputs (price/debt/equity live elsewhere).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_column, updated_at_column


class Budget(Base):
    """Per-acquisition budget header: status + the financial period the actuals were drawn from."""

    __tablename__ = "budgets"

    budget_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String, default="draft", nullable=False)  # draft | locked
    source_period_id: Mapped[str | None] = mapped_column(ForeignKey("financial_periods.period_id"))
    locked_by: Mapped[str | None] = mapped_column(String)
    locked_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class BudgetLine(Base):
    """One editable year-one cell: (acquisition, account, month) → amount + provenance. Prior-year
    is NOT stored here — it's computed on read from the mapped actuals."""

    __tablename__ = "budget_lines"
    __table_args__ = (
        UniqueConstraint("acquisition_id", "account_code", "month_index", name="uq_budget_cell"),
    )

    budget_line_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False
    )
    account_code: Mapped[str] = mapped_column(
        ForeignKey("gl_accounts.account_code"), nullable=False
    )
    month_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..12 (calendar month)
    year1_amount: Mapped[Decimal | None] = mapped_column(Numeric)
    source: Mapped[str] = mapped_column(String, nullable=False)  # actuals | default | placeholder
    default_rule_key: Mapped[str | None] = mapped_column(String)  # ties a row to a defaults rule
    is_overridden: Mapped[bool] = mapped_column(default=False, nullable=False)
    overridden_by: Mapped[str | None] = mapped_column(String)
    overridden_at: Mapped[datetime | None] = mapped_column()
    noi_placement: Mapped[str | None] = mapped_column(String)
    growth: Mapped[Decimal | None] = mapped_column(Numeric)
    note: Mapped[str | None] = mapped_column(Text)

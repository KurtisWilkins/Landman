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
    """One budget line (annual): a canonical GL OR a custom line item, with an editable prior-year
    and year-one amount + provenance. Prior-year defaults to the mapped actuals (computed on read)
    but can be overridden via ``prior_amount`` to correct an upload error. ``month_index`` is kept
    for back-compat and is 0 for an annual line. Custom (non-GL) lines have ``account_code`` NULL,
    a ``custom_label``, and a ``section`` so they still roll up; ``flagged_for_promotion`` marks
    them to add to the GL chart later. A line ``removed`` from the year-one projection keeps its
    prior value as reference (Q3) but contributes 0 to the year-one totals."""

    __tablename__ = "budget_lines"
    __table_args__ = (
        UniqueConstraint("acquisition_id", "account_code", "month_index", name="uq_budget_cell"),
    )

    budget_line_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False
    )
    # NULL for a custom (non-GL) line; otherwise a canonical GL.
    account_code: Mapped[str | None] = mapped_column(ForeignKey("gl_accounts.account_code"))
    custom_label: Mapped[str | None] = mapped_column(String)  # free-text name for a custom line
    section: Mapped[str | None] = mapped_column(String)  # Income | Expense (esp. for custom lines)
    flagged_for_promotion: Mapped[bool] = mapped_column(default=False, nullable=False)
    month_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 = annual line
    # Per-acquisition display order within a section (drag-to-reorder). NULL = never moved → falls
    # back to the GL chart order. Presentational only; the NOI roll-up is section-based.
    sort_order: Mapped[int | None] = mapped_column(Integer)
    prior_amount: Mapped[Decimal | None] = mapped_column(Numeric)  # override of the mapped actual
    year1_amount: Mapped[Decimal | None] = mapped_column(Numeric)
    removed: Mapped[bool] = mapped_column(default=False, nullable=False)  # out of year-one
    source: Mapped[str] = mapped_column(String, nullable=False)  # actuals | default | placeholder
    default_rule_key: Mapped[str | None] = mapped_column(String)  # ties a row to a defaults rule
    is_overridden: Mapped[bool] = mapped_column(default=False, nullable=False)
    overridden_by: Mapped[str | None] = mapped_column(String)
    overridden_at: Mapped[datetime | None] = mapped_column()
    noi_placement: Mapped[str | None] = mapped_column(String)
    growth: Mapped[Decimal | None] = mapped_column(Numeric)
    note: Mapped[str | None] = mapped_column(Text)

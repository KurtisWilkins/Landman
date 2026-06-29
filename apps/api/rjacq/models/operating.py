"""Per-acquisition operational inputs (defaults engine, Part 1).

A few defaults depend on per-property *drivers* that aren't always in the seller's P&L: the
billable unit mix (per-unit Repairs & Maintenance), the electric expense (utility bill-back), and
employee headcount (payroll budget). These are captured here, seeded from the OM where present and
prompted-for when absent, and every value is editable. Provenance (``om`` / ``manual`` /
``needs_input`` / ``actuals``) travels with each so the UI can flag what still needs input.

Shared inputs are not duplicated: these are *drivers*, consumed by the defaults engine; the dollar
results land on ``budget_lines`` like every other default.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_column, updated_at_column

# Provenance values for a driver (kept as plain strings, mirroring BudgetLine.source).
SOURCE_OM = "om"  # extracted from the offering memorandum
SOURCE_MANUAL = "manual"  # entered/edited by a person
SOURCE_ACTUALS = "actuals"  # seeded from the mapped prior-year P&L (electric)
SOURCE_NEEDS_INPUT = "needs_input"  # not captured yet — dependent default can't compute


class OperationalInputs(Base):
    """1:1 per-acquisition driver header: employee headcount + the electric expense. Unit groups
    live in their own table (1:many). NULL driver + ``needs_input`` source = surface the prompt."""

    __tablename__ = "operational_inputs"

    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), primary_key=True
    )
    # Payroll-budget driver: $85 × headcount × 12 (a budgeted allocation, not actual wages).
    employee_headcount: Mapped[int | None] = mapped_column(Integer)
    headcount_source: Mapped[str] = mapped_column(
        String, nullable=False, default=SOURCE_NEEDS_INPUT
    )
    # Utility-bill-back driver: the annual electric expense (the bill-back reads 62% of this).
    # Seeded from the mapped prior-year Electric (605410) actual where present; editable.
    electric_annual: Mapped[Decimal | None] = mapped_column(Numeric)
    electric_source: Mapped[str] = mapped_column(String, nullable=False, default=SOURCE_NEEDS_INPUT)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class UnitGroup(Base):
    """One billable-unit grouping on a deal (1:many). The category list is not fixed to three:
    a property can add finer sub-types if the OM provides them. ``billable`` (tents seed False)
    decides whether the group counts toward the per-unit drivers (R&M). ``count`` NULL = "needs
    input" — the dependent default can't compute until it's set."""

    __tablename__ = "unit_groups"

    unit_group_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String, nullable=False)  # rv_pad | cabin | glamping | …
    label: Mapped[str | None] = mapped_column(String)  # display name (esp. a custom sub-type)
    count: Mapped[int | None] = mapped_column(Integer)  # NULL = not captured yet
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default=SOURCE_NEEDS_INPUT)
    sort: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

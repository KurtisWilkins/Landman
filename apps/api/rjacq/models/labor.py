"""Per-deal labor plan (design doc §5.5, Labor tab).

One row per planned position. The pure ``underwriting.labor`` engine turns these into the dollar
amounts that feed the budget's Wages cluster (600140/600130/600155) and, for work campers, the
extended-stay revenue (400110) + campsite credit (421300) lines. Shared inputs are not duplicated;
labor rolls UP into the budget, which rolls into the stabilized NOI.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_column, updated_at_column


class LaborPosition(Base):
    """A planned position on a deal's staffing plan."""

    __tablename__ = "labor_positions"

    position_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False
    )
    # general_manager | front_desk | housekeeper | maintenance | events_coordinator | custom
    role: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str | None] = mapped_column(String)  # display name (esp. for a custom role)
    employment_type: Mapped[str] = mapped_column(String, nullable=False)  # full_time | part_time
    season: Mapped[str] = mapped_column(String, nullable=False)  # year_round | seasonal
    headcount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    hours_per_week: Mapped[Decimal | None] = mapped_column(Numeric)
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    is_work_camper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    benefits_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Work-camper comp: a campsite booked as extended-stay revenue offset by a campsite credit.
    site_weekly_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    campsite_credit_weekly: Mapped[Decimal | None] = mapped_column(Numeric)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    sort: Mapped[int | None] = mapped_column(Integer)
    # Provenance of the roster row: om (from the OM) | default (fallback roster) | manual (edited).
    source: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

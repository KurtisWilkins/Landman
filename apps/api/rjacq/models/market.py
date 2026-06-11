"""Market-sizing tables (§8.4 — Market).

Population rings: estimated population within 25/50/100/150-mile bands of a deal, auto-pulled
when a property is entered and overridable by the underwriter. Baseline (provider) + override
+ author + note are retained side by side (provenance), mirroring `assumptions`.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_column, updated_at_column

# The fixed ring radii (miles) for the initial-UW market view.
RING_RADII_MILES: tuple[int, ...] = (25, 50, 100, 150)


class PopulationRing(Base):
    __tablename__ = "population_rings"

    ring_id: Mapped[str] = mapped_column(String, primary_key=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.deal_id"), nullable=False)
    radius_mi: Mapped[int] = mapped_column(Integer, nullable=False)  # 25 | 50 | 100 | 150
    baseline_population: Mapped[int | None] = mapped_column(Integer)  # provider estimate
    override_population: Mapped[int | None] = mapped_column(Integer)
    is_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    overridden_by: Mapped[str | None] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String)  # provider name
    as_of: Mapped[date | None] = mapped_column(Date)  # estimate vintage
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

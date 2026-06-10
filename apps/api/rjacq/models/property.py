"""Property & operations tables (§8.4 — Property & operations).

``bookings`` (grain) and ``weekly_summary`` (rollup) coexist; the rollup is recomputed
from bookings when present, else loaded directly.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._columns import pg_enum
from .base import Base
from .enums import Channel, HookupLevel, UnitType, WeeklySummarySource


class Unit(Base):
    __tablename__ = "units"

    unit_id: Mapped[str] = mapped_column(String, primary_key=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.deal_id"), nullable=False)
    unit_type: Mapped[UnitType] = mapped_column(pg_enum(UnitType, "unit_type"))
    hookup_level: Mapped[HookupLevel | None] = mapped_column(pg_enum(HookupLevel, "hookup_level"))
    amp_rating: Mapped[int | None] = mapped_column(Integer)  # {20,30,50,null}
    count: Mapped[int | None] = mapped_column(Integer)
    occupancy_status: Mapped[str | None] = mapped_column(String)


class Amenity(Base):
    __tablename__ = "amenities"

    amenity_id: Mapped[str] = mapped_column(String, primary_key=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.deal_id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    present: Mapped[bool | None] = mapped_column(Boolean)
    condition: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)


class Booking(Base):
    __tablename__ = "bookings"

    booking_id: Mapped[str] = mapped_column(String, primary_key=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.deal_id"), nullable=False)
    site_id: Mapped[str | None] = mapped_column(String)
    unit_type: Mapped[UnitType | None] = mapped_column(pg_enum(UnitType, "booking_unit_type"))
    check_in: Mapped[date | None] = mapped_column(Date)
    check_out: Mapped[date | None] = mapped_column(Date)
    nights: Mapped[int | None] = mapped_column(Integer)
    gross_revenue: Mapped[Decimal | None] = mapped_column(Numeric)
    adr: Mapped[Decimal | None] = mapped_column(Numeric)
    channel: Mapped[Channel | None] = mapped_column(pg_enum(Channel, "channel"))
    booking_date: Mapped[date | None] = mapped_column(Date)
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class WeeklySummary(Base):
    __tablename__ = "weekly_summary"

    summary_id: Mapped[str] = mapped_column(String, primary_key=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.deal_id"), nullable=False)
    week_start: Mapped[date | None] = mapped_column(Date)
    available_unit_nights: Mapped[int | None] = mapped_column(Integer)
    occupied_unit_nights: Mapped[int | None] = mapped_column(Integer)
    occupancy_pct: Mapped[Decimal | None] = mapped_column(Numeric)
    adr: Mapped[Decimal | None] = mapped_column(Numeric)
    revpau: Mapped[Decimal | None] = mapped_column(Numeric)
    gross_revenue: Mapped[Decimal | None] = mapped_column(Numeric)
    source: Mapped[WeeklySummarySource | None] = mapped_column(
        pg_enum(WeeklySummarySource, "weekly_summary_source")
    )

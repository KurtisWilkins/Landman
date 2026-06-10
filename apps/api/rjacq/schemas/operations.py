"""Operations block schemas (§8.3 operations): bookings grain + weekly rollup."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from ..models.enums import Channel, WeeklySummarySource
from .common import ApiModel


class Booking(ApiModel):
    booking_id: str | None = None
    site_id: str | None = None
    unit_type: str | None = None
    check_in: date | None = None
    check_out: date | None = None
    nights: int | None = None
    gross_revenue: Decimal | None = None
    adr: Decimal | None = None
    channel: Channel | None = None
    booking_date: date | None = None
    lead_time_days: int | None = None


class WeeklySummary(ApiModel):
    week_start: date | None = None
    available_unit_nights: int | None = None
    occupied_unit_nights: int | None = None
    occupancy_pct: Decimal | None = None
    adr: Decimal | None = None
    revpau: Decimal | None = None
    gross_revenue: Decimal | None = None
    source: WeeklySummarySource | None = None


class OperationsDoc(BaseModel):
    bookings: list[Booking] = Field(default_factory=list)
    weekly_summary: list[WeeklySummary] = Field(default_factory=list)

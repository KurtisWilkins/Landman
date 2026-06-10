"""Core deal tables (§8.4 — Core)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._columns import pg_enum
from .base import Base, created_at_column, updated_at_column
from .enums import DealStatus, Phase, PhotoSource, PropertyType


class Deal(Base):
    __tablename__ = "deals"

    deal_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    property_type: Mapped[PropertyType] = mapped_column(
        pg_enum(PropertyType, "property_type"), nullable=False
    )
    address_line1: Mapped[str | None] = mapped_column(String)
    city: Mapped[str | None] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String)
    zip: Mapped[str | None] = mapped_column(String)
    lat: Mapped[float | None] = mapped_column(Numeric)
    lng: Mapped[float | None] = mapped_column(Numeric)
    site_count: Mapped[int | None] = mapped_column(Integer)
    ask_price: Mapped[Decimal | None] = mapped_column(Numeric)
    price_per_site: Mapped[Decimal | None] = mapped_column(Numeric)
    seller_name: Mapped[str | None] = mapped_column(String)
    date_received: Mapped[date | None] = mapped_column(Date)
    current_phase: Mapped[Phase] = mapped_column(pg_enum(Phase, "current_phase"), nullable=False)
    status: Mapped[DealStatus] = mapped_column(pg_enum(DealStatus, "deal_status"), nullable=False)
    thesis: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    photos: Mapped[list[DealPhoto]] = relationship(
        back_populates="deal", cascade="all, delete-orphan"
    )


class DealPhoto(Base):
    __tablename__ = "deal_photos"

    photo_id: Mapped[str] = mapped_column(String, primary_key=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.deal_id"), nullable=False)
    source: Mapped[PhotoSource] = mapped_column(pg_enum(PhotoSource, "photo_source"))
    url: Mapped[str] = mapped_column(String, nullable=False)
    caption: Mapped[str | None] = mapped_column(String)
    review_snippet: Mapped[str | None] = mapped_column(Text)
    sort: Mapped[int | None] = mapped_column(Integer)

    deal: Mapped[Deal] = relationship(back_populates="photos")

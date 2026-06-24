"""Core acquisition tables (§8.4 — Core)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._columns import pg_enum
from .base import Base, created_at_column, updated_at_column
from .enums import AcquisitionStatus, Phase, PhotoSource, PropertyType


class Acquisition(Base):
    __tablename__ = "acquisitions"

    acquisition_id: Mapped[str] = mapped_column(String, primary_key=True)
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
    # Negotiated/underwriting price that flows downstream (pro forma debt sizing + promote).
    # Distinct from ask_price (the OM ask); defaults to ask in the UI until set.
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric)
    price_per_site: Mapped[Decimal | None] = mapped_column(Numeric)
    seller_name: Mapped[str | None] = mapped_column(String)
    date_received: Mapped[date | None] = mapped_column(Date)
    current_phase: Mapped[Phase] = mapped_column(pg_enum(Phase, "current_phase"), nullable=False)
    status: Mapped[AcquisitionStatus] = mapped_column(
        pg_enum(AcquisitionStatus, "acquisition_status"), nullable=False
    )
    thesis: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # Soft-delete: archived deals leave the active pipeline but are never hard-deleted (recoverable
    # via restore). NULL = active. ``status`` (active/failed/…) is orthogonal and preserved.
    archived_at: Mapped[datetime | None] = mapped_column()
    archived_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    photos: Mapped[list[AcquisitionPhoto]] = relationship(
        back_populates="acquisition", cascade="all, delete-orphan"
    )


class AcquisitionPhoto(Base):
    __tablename__ = "acquisition_photos"

    photo_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False
    )
    source: Mapped[PhotoSource] = mapped_column(pg_enum(PhotoSource, "photo_source"))
    url: Mapped[str] = mapped_column(String, nullable=False)
    caption: Mapped[str | None] = mapped_column(String)
    review_snippet: Mapped[str | None] = mapped_column(Text)
    sort: Mapped[int | None] = mapped_column(Integer)

    acquisition: Mapped[Acquisition] = relationship(back_populates="photos")

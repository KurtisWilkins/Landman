"""Comp intelligence table (§8.4 — Comps)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Comp(Base):
    __tablename__ = "comps"

    comp_id: Mapped[str] = mapped_column(String, primary_key=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.deal_id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    lat: Mapped[float | None] = mapped_column(Numeric)
    lng: Mapped[float | None] = mapped_column(Numeric)
    distance_mi: Mapped[Decimal | None] = mapped_column(Numeric)
    avg_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric)
    amenity_rank: Mapped[int | None] = mapped_column(Integer)
    amenity_score: Mapped[int | None] = mapped_column(Integer)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    best_snippet: Mapped[str | None] = mapped_column(Text)
    worst_snippet: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scraped_at: Mapped[datetime | None] = mapped_column()
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

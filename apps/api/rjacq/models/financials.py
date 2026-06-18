"""Financial tables (§8.4 — Financials). Every line carries provenance."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._columns import pg_enum
from .base import Base, created_at_column
from .enums import AccountLevel, MapConfidence, NoiPlacement


class FinancialPeriod(Base):
    __tablename__ = "financial_periods"

    period_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(String)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    granularity: Mapped[str | None] = mapped_column(String)  # t12 | monthly | …
    # Versioning: each upload is a dated, retained version (never overwritten). The active one
    # for an acquisition is is_current=True; the rest stay queryable as history.
    source_filename: Mapped[str | None] = mapped_column(String)
    ingested_at: Mapped[datetime] = created_at_column()
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FinancialLine(Base):
    __tablename__ = "financial_lines"

    line_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False
    )
    period_id: Mapped[str] = mapped_column(
        ForeignKey("financial_periods.period_id"), nullable=False
    )
    # Nullable on purpose: unmapped lines persist and are surfaced for review (§5.3.6).
    account_code: Mapped[str | None] = mapped_column(ForeignKey("gl_accounts.account_code"))
    account_level: Mapped[AccountLevel | None] = mapped_column(
        pg_enum(AccountLevel, "fl_account_level")
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric)
    seller_source_line: Mapped[str | None] = mapped_column(Text)
    map_confidence: Mapped[MapConfidence | None] = mapped_column(
        pg_enum(MapConfidence, "map_confidence")
    )
    map_confidence_score: Mapped[Decimal | None] = mapped_column(Numeric)
    noi_placement: Mapped[NoiPlacement | None] = mapped_column(
        pg_enum(NoiPlacement, "noi_placement")
    )
    is_addback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    addback_amount: Mapped[Decimal | None] = mapped_column(Numeric)
    reviewed_by: Mapped[str | None] = mapped_column(String)
    reviewed_at: Mapped[datetime | None] = mapped_column()
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

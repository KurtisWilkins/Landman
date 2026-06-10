"""Workflow / gate tables (§8.4 — Workflow / gates)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ._columns import pg_enum
from .base import Base
from .enums import (
    GateItemStatus,
    Phase,
    RouteType,
    SuggestionStatus,
    SuggestionType,
)


class DealGateItem(Base):
    __tablename__ = "deal_gate_items"

    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.deal_id"), nullable=False)
    question_id: Mapped[str] = mapped_column(ForeignKey("gate_questions.question_id"))
    status: Mapped[GateItemStatus] = mapped_column(pg_enum(GateItemStatus, "gate_item_status"))
    blocking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    route_type: Mapped[RouteType | None] = mapped_column(pg_enum(RouteType, "gate_route_type"))
    routed_to: Mapped[str | None] = mapped_column(String)
    date_requested: Mapped[date | None] = mapped_column(Date)
    date_received: Mapped[date | None] = mapped_column(Date)
    acceptable: Mapped[bool | None] = mapped_column(Boolean)
    comments: Mapped[str | None] = mapped_column(Text)


class QuestionSuggestion(Base):
    __tablename__ = "question_suggestions"

    suggestion_id: Mapped[str] = mapped_column(String, primary_key=True)
    phase: Mapped[Phase] = mapped_column(pg_enum(Phase, "suggestion_phase"))
    type: Mapped[SuggestionType] = mapped_column(pg_enum(SuggestionType, "suggestion_type"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_by: Mapped[str | None] = mapped_column(String)
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[SuggestionStatus] = mapped_column(
        pg_enum(SuggestionStatus, "suggestion_status"), default=SuggestionStatus.PENDING
    )
    decided_by: Mapped[str | None] = mapped_column(String)
    decided_at: Mapped[datetime | None] = mapped_column()

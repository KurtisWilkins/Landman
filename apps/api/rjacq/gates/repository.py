"""Repository functions for the gates domain (DB access only, no business logic)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import Phase, RouteType, SuggestionStatus, SuggestionType
from ..models.gates import DealGateItem, QuestionSuggestion
from ..models.reference import GateQuestion


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


# ── gate_questions (shared config) ──────────────────────────────────────────


async def list_active_questions(
    session: AsyncSession, phase: Phase | None = None
) -> Sequence[GateQuestion]:
    stmt = select(GateQuestion).where(GateQuestion.active.is_(True))
    if phase is not None:
        stmt = stmt.where(GateQuestion.phase == phase)
    stmt = stmt.order_by(GateQuestion.phase, GateQuestion.question_id)
    return (await session.execute(stmt)).scalars().all()


async def add_question(
    session: AsyncSession,
    *,
    phase: Phase,
    text: str,
    category: str | None,
    blocking: bool,
    default_route_type: RouteType | None,
    created_by: str | None,
    approved_by: str | None,
) -> GateQuestion:
    question = GateQuestion(
        question_id=_new_id("gq"),
        phase=phase,
        category=category,
        text=text,
        blocking=blocking,
        default_route_type=default_route_type,
        active=True,
        created_by=created_by,
        approved_by=approved_by,
    )
    session.add(question)
    await session.flush()
    return question


# ── question_suggestions (suggest → approve) ────────────────────────────────


async def create_suggestion(
    session: AsyncSession,
    *,
    phase: Phase,
    type: SuggestionType,
    text: str,
    rationale: str | None,
    suggested_by: str | None,
) -> QuestionSuggestion:
    suggestion = QuestionSuggestion(
        suggestion_id=_new_id("qs"),
        phase=phase,
        type=type,
        text=text,
        rationale=rationale,
        suggested_by=suggested_by,
        status=SuggestionStatus.PENDING,
    )
    session.add(suggestion)
    await session.flush()
    return suggestion


async def get_suggestion(session: AsyncSession, suggestion_id: str) -> QuestionSuggestion | None:
    return await session.get(QuestionSuggestion, suggestion_id)


async def list_suggestions(
    session: AsyncSession,
    *,
    status: SuggestionStatus | None = None,
    phase: Phase | None = None,
) -> Sequence[QuestionSuggestion]:
    stmt = select(QuestionSuggestion)
    if status is not None:
        stmt = stmt.where(QuestionSuggestion.status == status)
    if phase is not None:
        stmt = stmt.where(QuestionSuggestion.phase == phase)
    stmt = stmt.order_by(QuestionSuggestion.suggestion_id)
    return (await session.execute(stmt)).scalars().all()


async def set_suggestion_decision(
    session: AsyncSession,
    suggestion: QuestionSuggestion,
    *,
    status: SuggestionStatus,
    decided_by: str | None,
) -> QuestionSuggestion:
    suggestion.status = status
    suggestion.decided_by = decided_by
    suggestion.decided_at = datetime.now(UTC)
    await session.flush()
    return suggestion


# ── deal_gate_items (per-deal) ──────────────────────────────────────────────


async def list_deal_gate_items(session: AsyncSession, deal_id: str) -> Sequence[DealGateItem]:
    stmt = select(DealGateItem).where(DealGateItem.deal_id == deal_id)
    return (await session.execute(stmt)).scalars().all()

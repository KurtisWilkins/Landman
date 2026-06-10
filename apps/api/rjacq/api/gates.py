"""Gate-question config and suggest→approve endpoints (§9, §5.7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import Principal, get_current_principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..gates import repository as repo
from ..gates import service
from ..gates.service import GateError
from ..models.enums import Phase, SuggestionStatus
from ..schemas.gates import (
    GateQuestion,
    QuestionSuggestionCreate,
    QuestionSuggestionDecision,
    QuestionSuggestionOut,
)

router = APIRouter(tags=["gates"])

# Domain error code → HTTP status. Conflicts (state/transition) are 409; bad input is 400.
_ERROR_STATUS = {
    "invalid_decision": status.HTTP_400_BAD_REQUEST,
    "phase_skip_not_allowed": status.HTTP_409_CONFLICT,
    "gate_not_cleared": status.HTTP_409_CONFLICT,
    "phase_terminal": status.HTTP_409_CONFLICT,
    "already_decided": status.HTTP_409_CONFLICT,
}


def _http_error(exc: GateError) -> HTTPException:
    return HTTPException(
        status_code=_ERROR_STATUS.get(exc.code, status.HTTP_409_CONFLICT),
        detail={"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}},
    )


@router.get("/gate-questions", response_model=list[GateQuestion])
async def list_gate_questions(
    phase: Phase | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> list[GateQuestion]:
    """Active gate-question config, optionally filtered by phase."""
    questions = await service.list_questions(session, phase)
    return [GateQuestion.model_validate(q) for q in questions]


@router.post("/question-suggestions", response_model=QuestionSuggestionOut)
async def suggest_question(
    body: QuestionSuggestionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> QuestionSuggestionOut:
    """Anyone may suggest a gate-question add/retire/edit."""
    suggestion = await service.submit_suggestion(
        session,
        phase=body.phase,
        type=body.type,
        text=body.text,
        rationale=body.rationale,
        suggested_by=principal.user_id,
    )
    await session.commit()
    return QuestionSuggestionOut.model_validate(suggestion)


@router.get("/question-suggestions", response_model=list[QuestionSuggestionOut])
async def list_question_suggestions(
    status_filter: SuggestionStatus | None = Query(default=None, alias="status"),
    phase: Phase | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.GATE_APPROVE)),
) -> list[QuestionSuggestionOut]:
    """Admin review queue: gate-question suggestions to approve/decline (§5.7).

    Contract note: this GET completes the suggest→approve surface (§9 is representative);
    it is additive — existing endpoints are unchanged.
    """
    suggestions = await service.list_suggestions(session, status=status_filter, phase=phase)
    return [QuestionSuggestionOut.model_validate(s) for s in suggestions]


@router.patch("/question-suggestions/{suggestion_id}", response_model=QuestionSuggestionOut)
async def decide_suggestion(
    suggestion_id: str,
    body: QuestionSuggestionDecision,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.GATE_APPROVE)),
) -> QuestionSuggestionOut:
    """Admin approves/declines a suggestion (only admin approves)."""
    suggestion = await repo.get_suggestion(session, suggestion_id)
    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Suggestion not found."}},
        )
    try:
        decided = await service.decide_suggestion(
            session, suggestion, status=body.status, decided_by=principal.user_id
        )
    except GateError as exc:
        await session.rollback()
        raise _http_error(exc) from exc
    await session.commit()
    return QuestionSuggestionOut.model_validate(decided)

"""Gate-question config and suggest→approve endpoints (§9, §5.7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..core.auth import Principal, get_current_principal
from ..core.rbac import Capability, require
from ..models.enums import Phase
from ..schemas.gates import (
    GateQuestion,
    QuestionSuggestionCreate,
    QuestionSuggestionDecision,
    QuestionSuggestionOut,
)
from ._stub import not_implemented

router = APIRouter(tags=["gates"])


@router.get("/gate-questions", response_model=list[GateQuestion])
async def list_gate_questions(
    phase: Phase | None = Query(default=None),
    _principal: Principal = Depends(get_current_principal),
) -> list[GateQuestion]:
    """Active gate-question config, optionally filtered by phase."""
    not_implemented("GET /gate-questions", phase="Phase 4 (gates)")


@router.post("/question-suggestions", response_model=QuestionSuggestionOut)
async def suggest_question(
    _body: QuestionSuggestionCreate,
    _principal: Principal = Depends(get_current_principal),
) -> QuestionSuggestionOut:
    """Anyone may suggest a gate-question add/retire/edit."""
    not_implemented("POST /question-suggestions", phase="Phase 4 (gates)")


@router.patch("/question-suggestions/{suggestion_id}", response_model=QuestionSuggestionOut)
async def decide_suggestion(
    suggestion_id: str,
    _body: QuestionSuggestionDecision,
    _principal: Principal = Depends(require(Capability.GATE_APPROVE)),
) -> QuestionSuggestionOut:
    """Admin approves/declines a suggestion (only admin approves)."""
    not_implemented("PATCH /question-suggestions/{id}", phase="Phase 4 (gates)")

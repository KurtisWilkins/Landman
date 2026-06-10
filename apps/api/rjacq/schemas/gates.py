"""Gate schemas (§8.3 gate) + question config and suggest→approve shapes (§9)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from ..models.enums import (
    GateItemStatus,
    Phase,
    RouteType,
    SuggestionStatus,
    SuggestionType,
)
from .common import ApiModel


class GateItem(ApiModel):
    question_id: str
    category: str | None = None
    status: GateItemStatus
    blocking: bool = False
    route_type: RouteType | None = None
    routed_to: str | None = None
    date_requested: date | None = None
    date_received: date | None = None
    acceptable: bool | None = None
    comments: str | None = None


class GateDoc(BaseModel):
    phase: Phase
    items: list[GateItem] = Field(default_factory=list)
    cleared: int = 0
    total: int = 0
    ready_to_advance: bool = False


class GateQuestion(ApiModel):
    question_id: str
    phase: Phase
    category: str | None = None
    text: str
    blocking: bool = False
    default_route_type: RouteType | None = None
    active: bool = True


class QuestionSuggestionCreate(BaseModel):
    """POST /question-suggestions — anyone may suggest."""

    phase: Phase
    type: SuggestionType
    text: str
    rationale: str | None = None


class QuestionSuggestionOut(ApiModel):
    suggestion_id: str
    phase: Phase
    type: SuggestionType
    text: str
    suggested_by: str | None = None
    rationale: str | None = None
    status: SuggestionStatus


class QuestionSuggestionDecision(BaseModel):
    """PATCH /question-suggestions/{id} — admin approves/declines."""

    status: SuggestionStatus  # approved | declined

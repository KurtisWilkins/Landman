"""Feedback widget, triage, enrichment, and dispatch endpoints (§9, §5.10–5.12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from ..core.auth import Principal
from ..core.rbac import Capability, require
from ..models.enums import FeedbackStatus, FeedbackType
from ..schemas.feedback import (
    CommentOut,
    DispatchOut,
    DispatchRequest,
    FeedbackAttachmentCreate,
    FeedbackCommentCreate,
    FeedbackCreate,
    FeedbackOut,
    FeedbackPatch,
)
from ._stub import not_implemented

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    _body: FeedbackCreate,
    _principal: Principal = Depends(require(Capability.FEEDBACK_SUBMIT)),
) -> FeedbackOut:
    """Widget submit; context (route/role/version/breadcrumbs/errors) auto-captured."""
    not_implemented("POST /feedback", phase="Phase 4 (feedback)")


@router.get("/feedback", response_model=list[FeedbackOut])
async def list_feedback(
    type: FeedbackType | None = Query(default=None),
    status_filter: FeedbackStatus | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    _principal: Principal = Depends(require(Capability.FEEDBACK_TRIAGE)),
) -> list[FeedbackOut]:
    """Triage queue, filterable by type/status/priority."""
    not_implemented("GET /feedback", phase="Phase 4 (feedback)")


@router.patch("/feedback/{feedback_id}", response_model=FeedbackOut)
async def patch_feedback(
    feedback_id: str,
    _body: FeedbackPatch,
    _principal: Principal = Depends(require(Capability.FEEDBACK_TRIAGE)),
) -> FeedbackOut:
    """Set status/priority/type/tags during triage."""
    not_implemented("PATCH /feedback/{id}", phase="Phase 4 (feedback)")


@router.post("/feedback/{feedback_id}/comments", response_model=CommentOut)
async def add_feedback_comment(
    feedback_id: str,
    _body: FeedbackCommentCreate,
    _principal: Principal = Depends(require(Capability.FEEDBACK_TRIAGE)),
) -> CommentOut:
    """Enrichment comment — builds the dispatch brief."""
    not_implemented("POST /feedback/{id}/comments", phase="Phase 4 (feedback)")


@router.post("/feedback/{feedback_id}/attachments", status_code=status.HTTP_201_CREATED)
async def add_feedback_attachment(
    feedback_id: str,
    _body: FeedbackAttachmentCreate,
    _principal: Principal = Depends(require(Capability.FEEDBACK_TRIAGE)),
) -> dict[str, str]:
    """Attach a screenshot/file (access-scoped storage; never logged — D-32)."""
    not_implemented("POST /feedback/{id}/attachments", phase="Phase 4 (feedback)")


@router.post("/feedback/{feedback_id}/dispatch", response_model=DispatchOut)
async def dispatch_feedback(
    feedback_id: str,
    _body: DispatchRequest,
    _principal: Principal = Depends(require(Capability.FEEDBACK_TRIAGE)),
) -> DispatchOut:
    """Package brief → create a GitHub issue mentioning @claude (§5.12). No auto-merge."""
    not_implemented("POST /feedback/{id}/dispatch", phase="Phase 4 (feedback)")

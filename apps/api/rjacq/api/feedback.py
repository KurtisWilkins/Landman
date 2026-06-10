"""Feedback widget, triage, enrichment, and dispatch endpoints (§9, §5.10–5.12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import Principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..feedback import repository as repo
from ..feedback import service
from ..feedback.github import build_github_client
from ..feedback.service import FeedbackError
from ..models.enums import FeedbackStatus, FeedbackType
from ..models.feedback import FeedbackItem
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

router = APIRouter(tags=["feedback"])

_ERROR_STATUS = {
    "not_ready": status.HTTP_409_CONFLICT,
    "dispatch_not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _http_error(exc: FeedbackError) -> HTTPException:
    return HTTPException(
        status_code=_ERROR_STATUS.get(exc.code, status.HTTP_409_CONFLICT),
        detail={"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}},
    )


async def _require_item(session: AsyncSession, feedback_id: str) -> FeedbackItem:
    item = await repo.get_item(session, feedback_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Feedback item not found."}},
        )
    return item


@router.post("/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.FEEDBACK_SUBMIT)),
) -> FeedbackOut:
    """Widget submit; context (route/role/version/breadcrumbs/errors) auto-captured."""
    item = await service.submit(
        session,
        type=body.type,
        title=body.title,
        description=body.description,
        context=body.context,
        submitted_by=principal.user_id,
        role=principal.role.value,
    )
    await session.commit()
    return FeedbackOut.model_validate(item)


@router.get("/feedback", response_model=list[FeedbackOut])
async def list_feedback(
    type: FeedbackType | None = Query(default=None),
    status_filter: FeedbackStatus | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.FEEDBACK_TRIAGE)),
) -> list[FeedbackOut]:
    """Triage queue, filterable by type/status/priority."""
    items = await service.list_feedback(session, type=type, status=status_filter, priority=priority)
    return [FeedbackOut.model_validate(i) for i in items]


@router.patch("/feedback/{feedback_id}", response_model=FeedbackOut)
async def patch_feedback(
    feedback_id: str,
    body: FeedbackPatch,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.FEEDBACK_TRIAGE)),
) -> FeedbackOut:
    """Set status/priority/type/tags during triage."""
    item = await _require_item(session, feedback_id)
    updated = await service.patch(
        session, item, status=body.status, priority=body.priority, type=body.type
    )
    await session.commit()
    return FeedbackOut.model_validate(updated)


@router.post("/feedback/{feedback_id}/comments", response_model=CommentOut)
async def add_feedback_comment(
    feedback_id: str,
    body: FeedbackCommentCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.FEEDBACK_TRIAGE)),
) -> CommentOut:
    """Enrichment comment — builds the dispatch brief."""
    await _require_item(session, feedback_id)
    comment = await service.add_comment(
        session, feedback_id=feedback_id, author=principal.user_id, body=body.body
    )
    await session.commit()
    return CommentOut.model_validate(comment)


@router.post("/feedback/{feedback_id}/attachments", status_code=status.HTTP_201_CREATED)
async def add_feedback_attachment(
    feedback_id: str,
    body: FeedbackAttachmentCreate,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.FEEDBACK_TRIAGE)),
) -> dict[str, str]:
    """Attach a screenshot/file (access-scoped storage; never logged — D-32)."""
    await _require_item(session, feedback_id)
    await service.add_attachment(session, feedback_id=feedback_id, kind=body.kind, url=body.url)
    await session.commit()
    return {"status": "attached"}


@router.post("/feedback/{feedback_id}/dispatch", response_model=DispatchOut)
async def dispatch_feedback(
    feedback_id: str,
    body: DispatchRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.FEEDBACK_TRIAGE)),
) -> DispatchOut:
    """Package brief → create a GitHub issue mentioning @claude (§5.12). No auto-merge."""
    item = await _require_item(session, feedback_id)
    try:
        dispatch_row = await service.dispatch(
            session,
            item,
            github_client=build_github_client(),
            dispatched_by=principal.user_id,
            additional_instructions=body.additional_instructions,
        )
    except FeedbackError as exc:
        await session.rollback()
        raise _http_error(exc) from exc
    await session.commit()
    return DispatchOut(
        dispatch_id=dispatch_row.dispatch_id,
        feedback_id=dispatch_row.feedback_id,
        github_issue_url=dispatch_row.github_issue_url,
        github_pr_url=dispatch_row.github_pr_url,
        status=dispatch_row.status,
        dispatched_at=dispatch_row.dispatched_at,
    )

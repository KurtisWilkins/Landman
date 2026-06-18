"""Feedback schemas (§8.4 feedback) + widget submit, triage, dispatch (§9, §5.10–5.12)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ..models.enums import FeedbackStatus, FeedbackType
from .common import ApiModel


class FeedbackContext(BaseModel):
    """Silently auto-captured on every submission (§5.10)."""

    page_route: str | None = None
    acquisition_id: str | None = None
    app_version: str | None = None
    browser: str | None = None
    os: str | None = None
    device: str | None = None
    viewport: str | None = None
    console_errors: list[dict[str, Any]] | None = None
    breadcrumbs: list[dict[str, Any]] | None = None
    last_api_error: dict[str, Any] | None = None


class FeedbackCreate(BaseModel):
    """POST /feedback — the user types only a short description; context is attached."""

    type: FeedbackType
    title: str | None = None
    description: str
    context: FeedbackContext | None = None


class FeedbackOut(ApiModel):
    feedback_id: str
    type: FeedbackType
    title: str | None = None
    description: str | None = None
    status: FeedbackStatus
    priority: str | None = None
    submitted_by: str | None = None
    role: str | None = None
    page_route: str | None = None
    acquisition_id: str | None = None
    app_version: str | None = None
    created_at: datetime | None = None


class FeedbackPatch(BaseModel):
    """PATCH /feedback/{id} — status/priority/type/tags (triage)."""

    status: FeedbackStatus | None = None
    priority: str | None = None
    type: FeedbackType | None = None
    tags: list[str] | None = None


class FeedbackCommentCreate(BaseModel):
    """POST /feedback/{id}/comments — enrichment builds the dispatch brief."""

    body: str


class FeedbackAttachmentCreate(BaseModel):
    """POST /feedback/{id}/attachments — screenshot/file (access-scoped, D-32)."""

    kind: str
    url: str


class DispatchRequest(BaseModel):
    """POST /feedback/{id}/dispatch — package brief → GitHub issue w/ @claude."""

    additional_instructions: str | None = None


class DispatchOut(BaseModel):
    dispatch_id: str
    feedback_id: str
    github_issue_url: str | None = None
    github_pr_url: str | None = None
    status: str | None = None
    dispatched_at: datetime | None = None


class CommentOut(ApiModel):
    comment_id: str
    author: str | None = None
    body: str | None = None
    created_at: datetime | None = None

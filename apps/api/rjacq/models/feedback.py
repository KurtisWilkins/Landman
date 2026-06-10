"""Feedback-loop tables (§8.4 — Feedback loop).

Context (console errors, breadcrumbs, last API error) is captured silently on submit.
Screenshots live in access-scoped storage and are never logged ([DECISION] D-32).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._columns import pg_enum
from .base import Base, created_at_column, updated_at_column
from .enums import FeedbackStatus, FeedbackType


class FeedbackItem(Base):
    __tablename__ = "feedback_items"

    feedback_id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[FeedbackType] = mapped_column(pg_enum(FeedbackType, "feedback_type"))
    title: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[FeedbackStatus] = mapped_column(
        pg_enum(FeedbackStatus, "feedback_status"), default=FeedbackStatus.NEW
    )
    priority: Mapped[str | None] = mapped_column(String)
    submitted_by: Mapped[str | None] = mapped_column(String)
    role: Mapped[str | None] = mapped_column(String)
    page_route: Mapped[str | None] = mapped_column(String)
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.deal_id"))
    app_version: Mapped[str | None] = mapped_column(String)
    browser: Mapped[str | None] = mapped_column(String)
    os: Mapped[str | None] = mapped_column(String)
    device: Mapped[str | None] = mapped_column(String)
    viewport: Mapped[str | None] = mapped_column(String)
    console_errors: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    breadcrumbs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_api_error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class FeedbackAttachment(Base):
    __tablename__ = "feedback_attachments"

    attachment_id: Mapped[str] = mapped_column(String, primary_key=True)
    feedback_id: Mapped[str] = mapped_column(
        ForeignKey("feedback_items.feedback_id"), nullable=False
    )
    kind: Mapped[str | None] = mapped_column(String)  # screenshot | file | log
    url: Mapped[str] = mapped_column(String, nullable=False)


class FeedbackComment(Base):
    __tablename__ = "feedback_comments"

    comment_id: Mapped[str] = mapped_column(String, primary_key=True)
    feedback_id: Mapped[str] = mapped_column(
        ForeignKey("feedback_items.feedback_id"), nullable=False
    )
    author: Mapped[str | None] = mapped_column(String)
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()


class FeedbackDispatch(Base):
    __tablename__ = "feedback_dispatch"

    dispatch_id: Mapped[str] = mapped_column(String, primary_key=True)
    feedback_id: Mapped[str] = mapped_column(
        ForeignKey("feedback_items.feedback_id"), nullable=False
    )
    target: Mapped[str | None] = mapped_column(String)  # e.g. "claude_code"
    brief: Mapped[str | None] = mapped_column(Text)
    github_issue_url: Mapped[str | None] = mapped_column(String)
    github_pr_url: Mapped[str | None] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String)
    dispatched_by: Mapped[str | None] = mapped_column(String)
    dispatched_at: Mapped[datetime | None] = mapped_column()
    updated_at: Mapped[datetime] = updated_at_column()

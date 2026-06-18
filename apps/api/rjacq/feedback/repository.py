"""Repository functions for the feedback domain (DB access only)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import FeedbackStatus, FeedbackType
from ..models.feedback import (
    FeedbackAttachment,
    FeedbackComment,
    FeedbackDispatch,
    FeedbackItem,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def create_item(
    session: AsyncSession,
    *,
    type: FeedbackType,
    title: str | None,
    description: str,
    submitted_by: str | None,
    role: str | None,
    page_route: str | None,
    acquisition_id: str | None,
    app_version: str | None,
    browser: str | None,
    os: str | None,
    device: str | None,
    viewport: str | None,
    console_errors: list[dict[str, Any]] | None,
    breadcrumbs: list[dict[str, Any]] | None,
    last_api_error: dict[str, Any] | None,
) -> FeedbackItem:
    item = FeedbackItem(
        feedback_id=_new_id("fb"),
        type=type,
        title=title,
        description=description,
        status=FeedbackStatus.NEW,
        submitted_by=submitted_by,
        role=role,
        page_route=page_route,
        acquisition_id=acquisition_id,
        app_version=app_version,
        browser=browser,
        os=os,
        device=device,
        viewport=viewport,
        console_errors=console_errors,
        breadcrumbs=breadcrumbs,
        last_api_error=last_api_error,
    )
    session.add(item)
    await session.flush()
    return item


async def get_item(session: AsyncSession, feedback_id: str) -> FeedbackItem | None:
    return await session.get(FeedbackItem, feedback_id)


async def list_items(
    session: AsyncSession,
    *,
    type: FeedbackType | None = None,
    status: FeedbackStatus | None = None,
    priority: str | None = None,
) -> Sequence[FeedbackItem]:
    stmt = select(FeedbackItem)
    if type is not None:
        stmt = stmt.where(FeedbackItem.type == type)
    if status is not None:
        stmt = stmt.where(FeedbackItem.status == status)
    if priority is not None:
        stmt = stmt.where(FeedbackItem.priority == priority)
    stmt = stmt.order_by(FeedbackItem.created_at.desc())
    return (await session.execute(stmt)).scalars().all()


async def add_comment(
    session: AsyncSession, *, feedback_id: str, author: str | None, body: str
) -> FeedbackComment:
    comment = FeedbackComment(
        comment_id=_new_id("fc"), feedback_id=feedback_id, author=author, body=body
    )
    session.add(comment)
    await session.flush()
    return comment


async def list_comments(session: AsyncSession, feedback_id: str) -> Sequence[FeedbackComment]:
    stmt = (
        select(FeedbackComment)
        .where(FeedbackComment.feedback_id == feedback_id)
        .order_by(FeedbackComment.created_at)
    )
    return (await session.execute(stmt)).scalars().all()


async def add_attachment(
    session: AsyncSession, *, feedback_id: str, kind: str, url: str
) -> FeedbackAttachment:
    attachment = FeedbackAttachment(
        attachment_id=_new_id("fa"), feedback_id=feedback_id, kind=kind, url=url
    )
    session.add(attachment)
    await session.flush()
    return attachment


async def create_dispatch(
    session: AsyncSession,
    *,
    feedback_id: str,
    target: str,
    brief: str,
    github_issue_url: str | None,
    status: str,
    dispatched_by: str | None,
) -> FeedbackDispatch:
    dispatch = FeedbackDispatch(
        dispatch_id=_new_id("fd"),
        feedback_id=feedback_id,
        target=target,
        brief=brief,
        github_issue_url=github_issue_url,
        status=status,
        dispatched_by=dispatched_by,
        dispatched_at=datetime.now(UTC),
    )
    session.add(dispatch)
    await session.flush()
    return dispatch


async def get_dispatch_by_issue_url(
    session: AsyncSession, issue_url: str
) -> FeedbackDispatch | None:
    stmt = select(FeedbackDispatch).where(FeedbackDispatch.github_issue_url == issue_url)
    return (await session.execute(stmt)).scalars().first()

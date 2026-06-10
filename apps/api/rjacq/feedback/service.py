"""Feedback-loop business logic (design doc §5.10–5.12).

Routers call these; DB access goes through ``repository`` and the GitHub call through the
injected ``GitHubClient``. Human-in-the-loop (CLAUDE.md): dispatch only ever opens an issue
for a human-reviewed PR — it never merges. PII discipline: we log ids/types/status only,
never descriptions, breadcrumbs, console payloads, or screenshot contents (D-32).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..models.enums import FeedbackStatus, FeedbackType
from ..models.feedback import FeedbackComment, FeedbackDispatch, FeedbackItem
from ..schemas.feedback import FeedbackContext
from . import repository as repo
from .github import GitHubClient

log = get_logger("feedback")

DISPATCH_TARGET = "claude_code"


class FeedbackError(Exception):
    """Domain error for the feedback flow. Carries a stable ``code``."""

    def __init__(self, code: str, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


# ── widget submit (§5.10) ───────────────────────────────────────────────────


async def submit(
    session: AsyncSession,
    *,
    type: FeedbackType,
    title: str | None,
    description: str,
    context: FeedbackContext | None,
    submitted_by: str | None,
    role: str | None,
) -> FeedbackItem:
    """Create a feedback item with silently-captured context.

    ``role``/``submitted_by`` come from the authenticated principal (server-trusted), never
    the client. Context is attached as-is; its contents are never logged.
    """
    ctx = context or FeedbackContext()
    item = await repo.create_item(
        session,
        type=type,
        title=title,
        description=description,
        submitted_by=submitted_by,
        role=role,
        page_route=ctx.page_route,
        deal_id=ctx.deal_id,
        app_version=ctx.app_version,
        browser=ctx.browser,
        os=ctx.os,
        device=ctx.device,
        viewport=ctx.viewport,
        console_errors=ctx.console_errors,
        breadcrumbs=ctx.breadcrumbs,
        last_api_error=ctx.last_api_error,
    )
    log.info("feedback.submitted", feedback_id=item.feedback_id, type=type.value)
    return item


# ── triage (§5.11) ──────────────────────────────────────────────────────────


async def list_feedback(
    session: AsyncSession,
    *,
    type: FeedbackType | None,
    status: FeedbackStatus | None,
    priority: str | None,
) -> Sequence[FeedbackItem]:
    return await repo.list_items(session, type=type, status=status, priority=priority)


async def patch(
    session: AsyncSession,
    item: FeedbackItem,
    *,
    status: FeedbackStatus | None,
    priority: str | None,
    type: FeedbackType | None,
) -> FeedbackItem:
    """Apply triage edits. ``tags`` from the request are not persisted: the §8
    ``feedback_items`` shape has no tags column — adding one is a schema decision, so we do
    not silently store them elsewhere. (Surface to the team via comments meanwhile.)
    """
    if status is not None:
        item.status = status
    if priority is not None:
        item.priority = priority
    if type is not None:
        item.type = type
    await session.flush()
    log.info("feedback.triaged", feedback_id=item.feedback_id, status=item.status.value)
    return item


async def add_comment(
    session: AsyncSession, *, feedback_id: str, author: str | None, body: str
) -> FeedbackComment:
    return await repo.add_comment(session, feedback_id=feedback_id, author=author, body=body)


async def add_attachment(session: AsyncSession, *, feedback_id: str, kind: str, url: str) -> None:
    # Screenshots/files live in access-scoped storage; we persist only a reference and
    # never log the contents (D-32).
    await repo.add_attachment(session, feedback_id=feedback_id, kind=kind, url=url)
    log.info("feedback.attachment_added", feedback_id=feedback_id, kind=kind)


# ── dispatch to Claude Code (§5.12) ─────────────────────────────────────────


def build_brief(
    item: FeedbackItem, comments: Sequence[FeedbackComment]
) -> tuple[str, str, list[str]]:
    """Assemble the structured GitHub issue (title, body, labels) for ``@claude``."""
    type_label = {
        FeedbackType.BUG: "bug",
        FeedbackType.FEATURE: "feature",
        FeedbackType.QUESTION: "question",
    }[item.type]
    title = item.title or f"{type_label}: {(item.description or '').splitlines()[0][:72]}"

    lines: list[str] = [f"## {type_label.capitalize()} report", ""]
    if item.description:
        lines += [item.description, ""]
    lines += ["## Context", ""]
    if item.page_route:
        lines.append(f"- Page / route: `{item.page_route}`")
    if item.deal_id:
        lines.append(f"- Deal: `{item.deal_id}`")
    if item.role:
        lines.append(f"- Reporter role: {item.role}")
    if item.app_version:
        lines.append(f"- App version: {item.app_version}")
    device_bits = ", ".join(b for b in (item.browser, item.os, item.viewport) if b)
    if device_bits:
        lines.append(f"- Device: {device_bits}")
    if item.last_api_error:
        lines.append(f"- Last API error: `{item.last_api_error}`")
    if comments:
        lines += ["", "## Enrichment notes"]
        lines += [f"- {c.body}" for c in comments if c.body]
    lines += [
        "",
        "---",
        "",
        "@claude please implement a fix/feature on a branch and open a PR referencing this "
        "issue. Follow CLAUDE.md. Do not merge — a human reviews every PR.",
    ]
    return title, "\n".join(lines), [type_label]


async def dispatch(
    session: AsyncSession,
    item: FeedbackItem,
    *,
    github_client: GitHubClient | None,
    dispatched_by: str | None,
    additional_instructions: str | None = None,
) -> FeedbackDispatch:
    """Package the brief, open a GitHub issue mentioning @claude, record the dispatch.

    Requires the item to be triaged to ``ready`` (the brief must be complete enough to act
    on, §5.11). Never auto-merges anything.
    """
    if item.status != FeedbackStatus.READY:
        raise FeedbackError(
            "not_ready",
            "Only a 'ready' item can be dispatched.",
            {"status": item.status.value},
        )
    if github_client is None:
        raise FeedbackError(
            "dispatch_not_configured",
            "GitHub dispatch is not configured (decision C-28/C-29).",
        )

    comments = await repo.list_comments(session, item.feedback_id)
    title, body, labels = build_brief(item, comments)
    if additional_instructions:
        body = f"{body}\n\n## Additional instructions\n{additional_instructions}"

    issue = await github_client.create_issue(title=title, body=body, labels=labels)
    dispatch_row = await repo.create_dispatch(
        session,
        feedback_id=item.feedback_id,
        target=DISPATCH_TARGET,
        brief=body,
        github_issue_url=issue.url,
        status="issue_open",
        dispatched_by=dispatched_by,
    )
    item.status = FeedbackStatus.DISPATCHED
    await session.flush()
    log.info(
        "feedback.dispatched",
        feedback_id=item.feedback_id,
        dispatch_id=dispatch_row.dispatch_id,
        issue_url=issue.url,
    )
    return dispatch_row


# ── webhook sync (§5.12.4) ──────────────────────────────────────────────────


async def apply_webhook(
    session: AsyncSession, *, event: str, payload: dict[str, Any]
) -> FeedbackDispatch | None:
    """Sync GitHub issue/PR state back to the dispatch + item. Returns the updated
    dispatch, or None when the event isn't correlated to a known dispatch.
    """
    if event == "issues":
        issue = payload.get("issue", {})
        dispatch_row = await repo.get_dispatch_by_issue_url(session, issue.get("html_url", ""))
        if dispatch_row is None:
            return None
        if payload.get("action") == "closed":
            dispatch_row.status = "closed"
            await _set_item_status(session, dispatch_row, FeedbackStatus.CLOSED)
        await session.flush()
        return dispatch_row

    if event == "pull_request":
        pr = payload.get("pull_request", {})
        body = pr.get("body") or ""
        dispatch_row = await _find_dispatch_for_pr(session, body)
        if dispatch_row is None:
            return None
        action = payload.get("action")
        if action in ("opened", "reopened"):
            dispatch_row.status = "pr_open"
            dispatch_row.github_pr_url = pr.get("html_url")
            await _set_item_status(session, dispatch_row, FeedbackStatus.IN_PROGRESS)
        elif action == "closed" and pr.get("merged"):
            dispatch_row.status = "merged"
            dispatch_row.github_pr_url = pr.get("html_url")
        await session.flush()
        return dispatch_row

    return None


async def _find_dispatch_for_pr(session: AsyncSession, pr_body: str) -> FeedbackDispatch | None:
    # claude-code-action opens a PR referencing the issue; match by the issue URL it embeds.
    from sqlalchemy import select

    stmt = select(FeedbackDispatch).where(FeedbackDispatch.github_issue_url.isnot(None))
    for dispatch_row in (await session.execute(stmt)).scalars().all():
        if dispatch_row.github_issue_url and dispatch_row.github_issue_url in pr_body:
            return dispatch_row
    return None


async def _set_item_status(
    session: AsyncSession, dispatch_row: FeedbackDispatch, status: FeedbackStatus
) -> None:
    item = await repo.get_item(session, dispatch_row.feedback_id)
    if item is not None:
        item.status = status

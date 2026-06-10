"""Feedback-loop tests (§5.10–5.12): context capture, triage, dispatch, webhook sync."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from rjacq.feedback import service
from rjacq.feedback.github import CreatedIssue, verify_signature
from rjacq.feedback.service import FeedbackError
from rjacq.models.deals import Deal
from rjacq.models.enums import DealStatus, FeedbackStatus, FeedbackType, Phase, PropertyType
from rjacq.models.feedback import FeedbackItem
from rjacq.schemas.feedback import FeedbackContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class FakeGitHubClient:
    """Records create_issue calls; returns a unique issue URL each call."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create_issue(self, *, title: str, body: str, labels: list[str]) -> CreatedIssue:
        self.calls.append({"title": title, "body": body, "labels": labels})
        n = len(self.calls)
        return CreatedIssue(number=n, url=f"https://github.com/o/r/issues/{uuid.uuid4().hex[:8]}")


async def _make_deal(session: AsyncSession) -> Deal:
    # Unique id: the test DB is shared across the session, so avoid PK collisions.
    deal = Deal(
        deal_id=f"dl_{uuid.uuid4().hex[:12]}",
        name="Test Park",
        property_type=PropertyType.RV_RESORT,
        current_phase=Phase.INITIAL_UW,
        status=DealStatus.ACTIVE,
    )
    session.add(deal)
    await session.flush()
    return deal


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _submit_ready(session: AsyncSession, **kw: object) -> FeedbackItem:
    item = await service.submit(
        session,
        type=kw.get("type", FeedbackType.BUG),  # type: ignore[arg-type]
        title=kw.get("title"),  # type: ignore[arg-type]
        description=kw.get("description", "Pro forma fails to render on mobile."),  # type: ignore[arg-type]
        context=kw.get("context"),  # type: ignore[arg-type]
        submitted_by="analyst_1",
        role="analyst",
    )
    item.status = FeedbackStatus.READY
    await session.flush()
    return item


# ── submit + silent context capture (§5.10) ─────────────────────────────────


async def test_submit_captures_context_and_trusted_role(session: AsyncSession) -> None:
    deal = await _make_deal(session)  # deal_id is a FK → deals
    ctx = FeedbackContext(
        page_route=f"/deals/{deal.deal_id}/proforma",
        deal_id=deal.deal_id,
        app_version="abc123",
        browser="Chrome",
        breadcrumbs=[{"e": "click"}],
        last_api_error={"status": 500},
    )
    item = await service.submit(
        session,
        type=FeedbackType.BUG,
        title=None,
        description="Numbers look wrong.",
        context=ctx,
        submitted_by="u_kurtis",
        role="admin",
    )
    await session.commit()
    assert item.status == FeedbackStatus.NEW
    assert item.page_route == f"/deals/{deal.deal_id}/proforma"
    assert item.deal_id == deal.deal_id
    assert item.breadcrumbs == [{"e": "click"}]
    assert item.last_api_error == {"status": 500}
    assert item.role == "admin"  # from the principal, not the client
    assert item.submitted_by == "u_kurtis"


async def test_triage_patch_updates_status(session: AsyncSession) -> None:
    item = await service.submit(
        session,
        type=FeedbackType.FEATURE,
        title="Export pro forma",
        description="Add CSV export.",
        context=None,
        submitted_by="a",
        role="analyst",
    )
    await session.commit()
    updated = await service.patch(
        session, item, status=FeedbackStatus.TRIAGED, priority="high", type=None
    )
    await session.commit()
    assert updated.status == FeedbackStatus.TRIAGED
    assert updated.priority == "high"


# ── dispatch (§5.12) ────────────────────────────────────────────────────────


def test_build_brief_mentions_claude_and_context() -> None:
    item = FeedbackItem(
        feedback_id="fb_1",
        type=FeedbackType.BUG,
        description="Crash on save.",
        status=FeedbackStatus.READY,
        page_route="/deals/dl_9/gates",
        role="analyst",
    )
    title, body, labels = service.build_brief(item, [])
    assert labels == ["bug"]
    assert "@claude" in body
    assert "/deals/dl_9/gates" in body
    assert "Do not merge" in body
    assert title


async def test_dispatch_requires_ready_status(session: AsyncSession) -> None:
    item = await service.submit(
        session,
        type=FeedbackType.BUG,
        title=None,
        description="x",
        context=None,
        submitted_by="a",
        role="analyst",
    )  # status NEW
    await session.commit()
    with pytest.raises(FeedbackError) as ei:
        await service.dispatch(
            session, item, github_client=FakeGitHubClient(), dispatched_by="kurtis"
        )
    assert ei.value.code == "not_ready"


async def test_dispatch_not_configured_when_no_client(session: AsyncSession) -> None:
    item = await _submit_ready(session)
    await session.commit()
    with pytest.raises(FeedbackError) as ei:
        await service.dispatch(session, item, github_client=None, dispatched_by="kurtis")
    assert ei.value.code == "dispatch_not_configured"


async def test_dispatch_opens_issue_and_records(session: AsyncSession) -> None:
    item = await _submit_ready(session, description="Pool photo 404s.")
    await session.commit()
    client = FakeGitHubClient()
    dispatch = await service.dispatch(session, item, github_client=client, dispatched_by="kurtis")
    await session.commit()
    assert len(client.calls) == 1
    assert "@claude" in client.calls[0]["body"]
    assert dispatch.github_issue_url is not None
    assert dispatch.github_issue_url.startswith("https://github.com/o/r/issues/")
    assert dispatch.status == "issue_open"
    assert item.status == FeedbackStatus.DISPATCHED  # never auto-merged


# ── webhook sync (§5.12.4) ──────────────────────────────────────────────────


async def test_webhook_pr_opened_and_merged(session: AsyncSession) -> None:
    item = await _submit_ready(session)
    await session.commit()
    dispatch = await service.dispatch(
        session, item, github_client=FakeGitHubClient(), dispatched_by="kurtis"
    )
    await session.commit()
    issue_url = dispatch.github_issue_url

    opened = await service.apply_webhook(
        session,
        event="pull_request",
        payload={
            "action": "opened",
            "pull_request": {
                "html_url": "https://github.com/o/r/pull/43",
                "body": f"Closes {issue_url}",
                "merged": False,
            },
        },
    )
    await session.commit()
    assert opened is not None
    assert opened.status == "pr_open"
    assert opened.github_pr_url == "https://github.com/o/r/pull/43"
    assert item.status == FeedbackStatus.IN_PROGRESS

    merged = await service.apply_webhook(
        session,
        event="pull_request",
        payload={
            "action": "closed",
            "pull_request": {
                "html_url": "https://github.com/o/r/pull/43",
                "body": f"Closes {issue_url}",
                "merged": True,
            },
        },
    )
    await session.commit()
    assert merged is not None
    assert merged.status == "merged"


async def test_webhook_unknown_dispatch_is_ignored(session: AsyncSession) -> None:
    result = await service.apply_webhook(
        session,
        event="issues",
        payload={"action": "closed", "issue": {"html_url": "https://github.com/o/r/issues/999"}},
    )
    assert result is None


# ── signature verification ──────────────────────────────────────────────────


def test_verify_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    import hmac

    from rjacq.feedback import github as gh

    monkeypatch.setattr(gh.settings, "github_webhook_secret", "s3cr3t")
    body = b'{"hello":"world"}'
    good = "sha256=" + hmac.new(b"s3cr3t", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, good) is True
    assert verify_signature(body, "sha256=deadbeef") is False
    assert verify_signature(body, None) is False


def test_verify_signature_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    from rjacq.feedback import github as gh

    monkeypatch.setattr(gh.settings, "github_webhook_secret", None)
    assert verify_signature(b"x", "sha256=whatever") is False

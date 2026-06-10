"""Gates domain tests (§5.7): blocking/no-skip logic and suggest→approve."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from rjacq.gates import service
from rjacq.gates.service import GateError
from rjacq.models.enums import (
    GateItemStatus,
    Phase,
    SuggestionStatus,
    SuggestionType,
)
from rjacq.models.gates import DealGateItem
from rjacq.models.reference import GateQuestion
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _item(blocking: bool, status: GateItemStatus, qid: str = "q") -> DealGateItem:
    return DealGateItem(
        item_id=f"gi_{qid}", deal_id="dl_x", question_id=qid, status=status, blocking=blocking
    )


# ── pure logic (no DB) ──────────────────────────────────────────────────────


def test_next_phase_order_and_terminal() -> None:
    assert service.next_phase(Phase.INITIAL_UW) is Phase.LOI
    assert service.next_phase(Phase.DUE_DILIGENCE) is Phase.CLOSE
    assert service.next_phase(Phase.CLOSE) is None


def test_readiness_blocking_open_blocks() -> None:
    items = [
        _item(True, GateItemStatus.ACCEPTED, "a"),
        _item(True, GateItemStatus.OPEN, "b"),
        _item(False, GateItemStatus.OPEN, "c"),
    ]
    cleared, total, ready = service.evaluate_readiness(items)
    assert (cleared, total, ready) == (1, 3, False)


def test_readiness_waived_counts_as_cleared() -> None:
    items = [_item(True, GateItemStatus.ACCEPTED, "a"), _item(True, GateItemStatus.WAIVED, "b")]
    cleared, total, ready = service.evaluate_readiness(items)
    assert (cleared, total, ready) == (2, 2, True)


def test_non_blocking_open_does_not_block() -> None:
    items = [_item(True, GateItemStatus.ACCEPTED, "a"), _item(False, GateItemStatus.OPEN, "b")]
    _, _, ready = service.evaluate_readiness(items)
    assert ready is True


def test_cannot_skip_a_phase() -> None:
    with pytest.raises(GateError) as ei:
        service.assert_can_advance(Phase.INITIAL_UW, Phase.CONTRACT, [])
    assert ei.value.code == "phase_skip_not_allowed"
    assert ei.value.detail["allowed_phase"] == Phase.LOI.value


def test_cannot_advance_with_open_blocking_item() -> None:
    items = [_item(True, GateItemStatus.OPEN, "rent_roll")]
    with pytest.raises(GateError) as ei:
        service.assert_can_advance(Phase.INITIAL_UW, Phase.LOI, items)
    assert ei.value.code == "gate_not_cleared"
    assert "rent_roll" in ei.value.detail["open_blocking_items"]


def test_advance_allowed_when_blocking_cleared() -> None:
    items = [_item(True, GateItemStatus.ACCEPTED, "a"), _item(False, GateItemStatus.OPEN, "b")]
    # Should not raise.
    service.assert_can_advance(Phase.INITIAL_UW, Phase.LOI, items)


def test_cannot_advance_past_final_phase() -> None:
    with pytest.raises(GateError) as ei:
        service.assert_can_advance(Phase.CLOSE, Phase.CLOSE, [])
    assert ei.value.code == "phase_terminal"


# ── suggest → approve (real Postgres) ───────────────────────────────────────


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_approving_add_suggestion_joins_live_set(session: AsyncSession) -> None:
    suggestion = await service.submit_suggestion(
        session,
        phase=Phase.DUE_DILIGENCE,
        type=SuggestionType.ADD,
        text="Confirm septic capacity and permits.",
        rationale="RV parks hinge on septic.",
        suggested_by="analyst_1",
    )
    await session.commit()
    assert suggestion.status == SuggestionStatus.PENDING  # never auto-applied

    before = {q.question_id for q in await service.list_questions(session, Phase.DUE_DILIGENCE)}
    decided = await service.decide_suggestion(
        session, suggestion, status=SuggestionStatus.APPROVED, decided_by="kurtis"
    )
    await session.commit()
    assert decided.status == SuggestionStatus.APPROVED

    after = await service.list_questions(session, Phase.DUE_DILIGENCE)
    new = [q for q in after if q.question_id not in before]
    assert len(new) == 1
    assert new[0].text == "Confirm septic capacity and permits."
    assert new[0].active is True
    assert new[0].approved_by == "kurtis"


async def test_declined_suggestion_adds_no_question(session: AsyncSession) -> None:
    suggestion = await service.submit_suggestion(
        session,
        phase=Phase.LOI,
        type=SuggestionType.ADD,
        text="Some declined item.",
        rationale=None,
        suggested_by="analyst_2",
    )
    await session.commit()
    count_before = len((await session.execute(select(GateQuestion))).scalars().all())
    await service.decide_suggestion(
        session, suggestion, status=SuggestionStatus.DECLINED, decided_by="kurtis"
    )
    await session.commit()
    count_after = len((await session.execute(select(GateQuestion))).scalars().all())
    assert count_after == count_before


async def test_cannot_decide_twice(session: AsyncSession) -> None:
    suggestion = await service.submit_suggestion(
        session,
        phase=Phase.LOI,
        type=SuggestionType.ADD,
        text="Decide-twice item.",
        rationale=None,
        suggested_by="analyst_3",
    )
    await session.commit()
    await service.decide_suggestion(
        session, suggestion, status=SuggestionStatus.APPROVED, decided_by="kurtis"
    )
    await session.commit()
    with pytest.raises(GateError) as ei:
        await service.decide_suggestion(
            session, suggestion, status=SuggestionStatus.DECLINED, decided_by="kurtis"
        )
    assert ei.value.code == "already_decided"


async def test_list_suggestions_filters_by_status(session: AsyncSession) -> None:
    pending = await service.submit_suggestion(
        session,
        phase=Phase.CONTRACT,
        type=SuggestionType.ADD,
        text="A pending review-queue item.",
        rationale=None,
        suggested_by="analyst_q",
    )
    other = await service.submit_suggestion(
        session,
        phase=Phase.CONTRACT,
        type=SuggestionType.ADD,
        text="A decided item.",
        rationale=None,
        suggested_by="analyst_q",
    )
    await service.decide_suggestion(
        session, other, status=SuggestionStatus.DECLINED, decided_by="kurtis"
    )
    await session.commit()

    pending_only = await service.list_suggestions(
        session, status=SuggestionStatus.PENDING, phase=None
    )
    ids = {s.suggestion_id for s in pending_only}
    assert pending.suggestion_id in ids
    assert other.suggestion_id not in ids
    assert all(s.status == SuggestionStatus.PENDING for s in pending_only)

"""Gates business logic (design doc §5.7).

Pure, side-effect-light functions for gate readiness and phase-advancement guarding, plus
the suggest→approve workflow. Routers call these; DB access goes through ``repository``.

Human-in-the-loop (CLAUDE.md): this module *guards* advancement and *applies* an admin's
approval — it never auto-advances a acquisition or auto-approves a suggestion.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import (
    GateItemStatus,
    Phase,
    SuggestionStatus,
    SuggestionType,
)
from ..models.gates import AcquisitionGateItem, QuestionSuggestion
from ..models.reference import GateQuestion
from . import repository as repo

# Canonical phase order (§8.2 / §5.7). A acquisition advances one step at a time and cannot skip.
PHASE_ORDER: tuple[Phase, ...] = (
    Phase.INITIAL_UW,
    Phase.LOI,
    Phase.CONTRACT,
    Phase.DUE_DILIGENCE,
    Phase.CLOSE,
)

# A blocking gate item counts as cleared only when accepted or explicitly waived.
_CLEARED_STATUSES: frozenset[GateItemStatus] = frozenset(
    {GateItemStatus.ACCEPTED, GateItemStatus.WAIVED}
)


class GateError(Exception):
    """Domain error for invalid gate transitions. Carries a stable ``code``."""

    def __init__(self, code: str, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


def next_phase(current: Phase) -> Phase | None:
    """The single allowed next phase, or None if already at the final phase."""
    idx = PHASE_ORDER.index(current)
    return PHASE_ORDER[idx + 1] if idx + 1 < len(PHASE_ORDER) else None


def evaluate_readiness(items: Iterable[AcquisitionGateItem]) -> tuple[int, int, bool]:
    """Return ``(cleared, total, ready_to_advance)`` for a acquisition's gate items.

    ``ready_to_advance`` is True only when **every blocking item** is cleared (accepted or
    waived). Non-blocking items never hold up advancement but still count toward totals.
    """
    items = list(items)
    total = len(items)
    cleared = sum(1 for i in items if i.status in _CLEARED_STATUSES)
    blocking_open = [i for i in items if i.blocking and i.status not in _CLEARED_STATUSES]
    return cleared, total, len(blocking_open) == 0


def assert_can_advance(
    current_phase: Phase,
    target_phase: Phase,
    items: Iterable[AcquisitionGateItem],
) -> None:
    """Raise ``GateError`` unless the acquisition may advance from current to target.

    Enforces two rules (§5.7): the target must be the immediate next phase (no skipping),
    and all blocking items for the current phase must be cleared first.
    """
    expected = next_phase(current_phase)
    if expected is None:
        raise GateError(
            "phase_terminal",
            f"Acquisition is already at the final phase ({current_phase.value}).",
            {"current_phase": current_phase.value},
        )
    if target_phase != expected:
        raise GateError(
            "phase_skip_not_allowed",
            "A acquisition advances one phase at a time and cannot skip.",
            {
                "current_phase": current_phase.value,
                "requested_phase": target_phase.value,
                "allowed_phase": expected.value,
            },
        )
    _cleared, _total, ready = evaluate_readiness(items)
    if not ready:
        blocking_open = [
            i.question_id for i in items if i.blocking and i.status not in _CLEARED_STATUSES
        ]
        raise GateError(
            "gate_not_cleared",
            "Blocking gate items remain open for the current phase.",
            {"open_blocking_items": blocking_open},
        )


# ── suggest → approve (§5.7) ────────────────────────────────────────────────


async def submit_suggestion(
    session: AsyncSession,
    *,
    phase: Phase,
    type: SuggestionType,
    text: str,
    rationale: str | None,
    suggested_by: str | None,
) -> QuestionSuggestion:
    """Anyone may submit a suggestion; it starts in ``pending`` (never auto-applied)."""
    return await repo.create_suggestion(
        session,
        phase=phase,
        type=type,
        text=text,
        rationale=rationale,
        suggested_by=suggested_by,
    )


async def decide_suggestion(
    session: AsyncSession,
    suggestion: QuestionSuggestion,
    *,
    status: SuggestionStatus,
    decided_by: str | None,
) -> QuestionSuggestion:
    """Admin approves or declines a suggestion.

    On approval of an ``add`` suggestion, a new active gate question joins the live set
    going forward — historical acquisitions' gate items are untouched (§5.7). ``retire``/``edit``
    approvals are recorded for an admin to apply against a specific question, since the §8
    ``question_suggestions`` shape carries no target ``question_id`` to mutate safely.
    """
    if status not in (SuggestionStatus.APPROVED, SuggestionStatus.DECLINED):
        raise GateError(
            "invalid_decision",
            "A suggestion decision must be 'approved' or 'declined'.",
            {"status": status.value},
        )
    if suggestion.status != SuggestionStatus.PENDING:
        raise GateError(
            "already_decided",
            "This suggestion has already been decided.",
            {"status": suggestion.status.value},
        )

    await repo.set_suggestion_decision(session, suggestion, status=status, decided_by=decided_by)
    if status == SuggestionStatus.APPROVED and suggestion.type == SuggestionType.ADD:
        await repo.add_question(
            session,
            phase=suggestion.phase,
            text=suggestion.text,
            category=None,
            blocking=False,  # blocking status set by admin later; never guessed here
            default_route_type=None,
            created_by=suggestion.suggested_by,
            approved_by=decided_by,
        )
    return suggestion


async def list_questions(session: AsyncSession, phase: Phase | None) -> Sequence[GateQuestion]:
    return await repo.list_active_questions(session, phase)


async def list_suggestions(
    session: AsyncSession,
    *,
    status: SuggestionStatus | None,
    phase: Phase | None,
) -> Sequence[QuestionSuggestion]:
    """The admin review queue — suggestions to approve/decline (§5.7)."""
    return await repo.list_suggestions(session, status=status, phase=phase)

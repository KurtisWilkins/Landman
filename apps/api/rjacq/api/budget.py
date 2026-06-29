"""Year-one budget endpoints (design doc §5.5, §9) — the two-column annual grid."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import Principal, get_current_principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..schemas.budget import BudgetDoc, BudgetLineCreate, BudgetLinePatch
from ..underwriting import budget_service
from ..underwriting import service as underwriting

router = APIRouter(tags=["budget"])


def _bad_request(exc: budget_service.BudgetError) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND if exc.code == "line_not_found" else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(
        status_code=code, detail={"error": {"code": exc.code, "message": exc.message}}
    )


@router.get("/acquisitions/{acquisition_id}/budget", response_model=BudgetDoc)
async def get_budget(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> BudgetDoc:
    """The two-column prior-year / year-one grid: each line's prior actuals (editable, defaults to
    the mapped P&L) beside the editable year-one projection, with provenance + the NOI roll-up."""
    return await budget_service.get_budget(session, acquisition_id)


@router.post("/acquisitions/{acquisition_id}/budget/seed", response_model=BudgetDoc)
async def seed_budget(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> BudgetDoc:
    """Prefill annual rows from the mapped prior-year actuals + the defaults engine (idempotent)."""
    return await budget_service.seed_budget(session, acquisition_id)


@router.post("/acquisitions/{acquisition_id}/budget/line", response_model=BudgetDoc)
async def add_budget_line(
    acquisition_id: str,
    body: BudgetLineCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> BudgetDoc:
    """Add a row — a canonical GL or a custom (flagged) line item."""
    try:
        return await budget_service.add_line(session, acquisition_id, body, actor=principal.user_id)
    except budget_service.BudgetError as exc:
        raise _bad_request(exc) from exc


@router.patch("/acquisitions/{acquisition_id}/budget/line", response_model=BudgetDoc)
async def patch_budget_line(
    acquisition_id: str,
    body: BudgetLinePatch,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> BudgetDoc:
    """Edit a line's prior and/or year-one amount."""
    try:
        return await budget_service.patch_line(
            session, acquisition_id, body, actor=principal.user_id
        )
    except budget_service.BudgetError as exc:
        raise _bad_request(exc) from exc


@router.delete("/acquisitions/{acquisition_id}/budget/line/{line_id}", response_model=BudgetDoc)
async def remove_budget_line(
    acquisition_id: str,
    line_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> BudgetDoc:
    """Remove a row (custom → deleted; GL → dropped from year-one, prior kept)."""
    try:
        return await budget_service.remove_line(
            session, acquisition_id, line_id, actor=principal.user_id
        )
    except budget_service.BudgetError as exc:
        raise _bad_request(exc) from exc


@router.post(
    "/acquisitions/{acquisition_id}/budget/line/{line_id}/revert-default", response_model=BudgetDoc
)
async def revert_budget_line_to_default(
    acquisition_id: str,
    line_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> BudgetDoc:
    """Clear a manual edit and re-link the line to its default rule (recompute from drivers)."""
    try:
        return await budget_service.revert_to_default(
            session, acquisition_id, line_id, actor=principal.user_id
        )
    except budget_service.BudgetError as exc:
        raise _bad_request(exc) from exc


@router.post("/acquisitions/{acquisition_id}/budget/apply-defaults", response_model=BudgetDoc)
async def apply_budget_defaults(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> BudgetDoc:
    """Re-run the defaults engine against the current drivers (manual lines untouched)."""
    return await budget_service.apply_defaults(session, acquisition_id, actor=principal.user_id)


@router.post("/acquisitions/{acquisition_id}/budget/lock", response_model=BudgetDoc)
async def lock_budget(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> BudgetDoc:
    """Lock the budget (gated on zero placeholders + zero unmapped lines), then roll it up to the
    stabilized NOI and recompute the pro forma / returns."""
    try:
        await budget_service.lock(session, acquisition_id, by=principal.user_id)
    except budget_service.BudgetError as exc:
        code = status.HTTP_404_NOT_FOUND if exc.code == "not_seeded" else status.HTTP_409_CONFLICT
        raise HTTPException(
            status_code=code, detail={"error": {"code": exc.code, "message": exc.message}}
        ) from exc
    await underwriting.save_inputs_and_recompute(session, acquisition_id, {})
    return await budget_service.get_budget(session, acquisition_id)


@router.post("/acquisitions/{acquisition_id}/budget/unlock", response_model=BudgetDoc)
async def unlock_budget(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> BudgetDoc:
    """Re-open a locked budget for editing; pro forma reverts to the bridge until re-lock."""
    await budget_service.unlock(session, acquisition_id)
    await underwriting.save_inputs_and_recompute(session, acquisition_id, {})
    return await budget_service.get_budget(session, acquisition_id)

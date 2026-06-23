"""Year-one budget endpoints (design doc §5.5, §9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import Principal, get_current_principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..schemas.budget import BudgetCellUpdate, BudgetDoc
from ..underwriting import budget_service
from ..underwriting import service as underwriting

router = APIRouter(tags=["budget"])


@router.get("/acquisitions/{acquisition_id}/budget", response_model=BudgetDoc)
async def get_budget(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> BudgetDoc:
    """The prior-year-vs-year-one budget: each GL's prior-year actuals (read-only, computed)
    beside the editable year-one projection, month by month, with variance + provenance."""
    return await budget_service.get_budget(session, acquisition_id)


@router.post("/acquisitions/{acquisition_id}/budget/seed", response_model=BudgetDoc)
async def seed_budget(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> BudgetDoc:
    """Prefill year-one from the mapped prior-year actuals (idempotent; never clobbers edits)."""
    return await budget_service.seed_budget(session, acquisition_id)


@router.patch("/acquisitions/{acquisition_id}/budget", response_model=BudgetDoc)
async def patch_budget(
    acquisition_id: str,
    body: BudgetCellUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> BudgetDoc:
    """Edit one year-one cell (flips it to a human override)."""
    try:
        return await budget_service.patch_cell(
            session, acquisition_id, body, actor=principal.user_id
        )
    except budget_service.BudgetError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc


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

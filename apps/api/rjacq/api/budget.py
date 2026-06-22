"""Year-one budget endpoints (design doc §5.5, §9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import Principal, get_current_principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..schemas.budget import BudgetCellUpdate, BudgetDoc
from ..underwriting import budget_service

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
    return await budget_service.patch_cell(session, acquisition_id, body, actor=principal.user_id)

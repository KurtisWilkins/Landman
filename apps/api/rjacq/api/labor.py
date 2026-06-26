"""Labor plan endpoints (design doc §5.5, Labor tab)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import Principal, get_current_principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..schemas.labor import LaborDoc, LaborPositionCreate, LaborPositionPatch
from ..underwriting import labor_service

router = APIRouter(tags=["labor"])


def _bad_request(exc: labor_service.LaborError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if exc.code == "not_found" else status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=code, detail={"error": {"code": exc.code, "message": exc.message}}
    )


@router.get("/acquisitions/{acquisition_id}/labor", response_model=LaborDoc)
async def get_labor(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> LaborDoc:
    """The deal's staffing plan: positions + the rolled-up labor totals (feeds the budget Wages
    cluster) and prior-year labor from the mapped P&L."""
    return await labor_service.get_labor(session, acquisition_id)


@router.post("/acquisitions/{acquisition_id}/labor/seed", response_model=LaborDoc)
async def seed_labor(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> LaborDoc:
    """Seed the default staffing scenario (idempotent)."""
    return await labor_service.seed_default_staffing(
        session, acquisition_id, actor=principal.user_id
    )


@router.post("/acquisitions/{acquisition_id}/labor/position", response_model=LaborDoc)
async def add_position(
    acquisition_id: str,
    body: LaborPositionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> LaborDoc:
    """Add a position to the plan."""
    return await labor_service.add_position(session, acquisition_id, body, actor=principal.user_id)


@router.patch("/acquisitions/{acquisition_id}/labor/position", response_model=LaborDoc)
async def patch_position(
    acquisition_id: str,
    body: LaborPositionPatch,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> LaborDoc:
    """Edit a position."""
    try:
        return await labor_service.patch_position(
            session, acquisition_id, body, actor=principal.user_id
        )
    except labor_service.LaborError as exc:
        raise _bad_request(exc) from exc


@router.delete(
    "/acquisitions/{acquisition_id}/labor/position/{position_id}", response_model=LaborDoc
)
async def remove_position(
    acquisition_id: str,
    position_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> LaborDoc:
    """Remove a position from the plan."""
    try:
        return await labor_service.remove_position(
            session, acquisition_id, position_id, actor=principal.user_id
        )
    except labor_service.LaborError as exc:
        raise _bad_request(exc) from exc

"""Operational-input endpoints (defaults engine, Part 1) — the per-deal driver capture panel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import Principal, get_current_principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..schemas.operating import OperatingDoc, OperatingPatch, UnitGroupCreate, UnitGroupPatch
from ..underwriting import operating_service

router = APIRouter(tags=["operating"])


def _bad_request(exc: operating_service.OperatingError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if exc.code == "not_found" else status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=code, detail={"error": {"code": exc.code, "message": exc.message}}
    )


@router.get("/acquisitions/{acquisition_id}/operating", response_model=OperatingDoc)
async def get_operating(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> OperatingDoc:
    """The Operating Inputs panel: unit groups + headcount + electric, with driver totals and the
    'needs input' flags that gate the dependent defaults."""
    return await operating_service.get_operating(session, acquisition_id)


@router.post("/acquisitions/{acquisition_id}/operating/seed", response_model=OperatingDoc)
async def seed_operating(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> OperatingDoc:
    """Seed the panel from the OM unit mix + the mapped prior-year Electric (idempotent)."""
    return await operating_service.seed_operating(session, acquisition_id, actor=principal.user_id)


@router.patch("/acquisitions/{acquisition_id}/operating", response_model=OperatingDoc)
async def patch_operating(
    acquisition_id: str,
    body: OperatingPatch,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> OperatingDoc:
    """Edit the headcount and/or electric driver (flips the edited field to manual)."""
    return await operating_service.patch_operating(
        session, acquisition_id, body, actor=principal.user_id
    )


@router.post("/acquisitions/{acquisition_id}/operating/unit-group", response_model=OperatingDoc)
async def add_unit_group(
    acquisition_id: str,
    body: UnitGroupCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> OperatingDoc:
    """Add a unit group — a default category or a custom sub-type."""
    try:
        return await operating_service.add_unit_group(
            session, acquisition_id, body, actor=principal.user_id
        )
    except operating_service.OperatingError as exc:
        raise _bad_request(exc) from exc


@router.patch("/acquisitions/{acquisition_id}/operating/unit-group", response_model=OperatingDoc)
async def patch_unit_group(
    acquisition_id: str,
    body: UnitGroupPatch,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> OperatingDoc:
    """Edit a unit group's count / billable / label (flips it to manual)."""
    try:
        return await operating_service.patch_unit_group(
            session, acquisition_id, body, actor=principal.user_id
        )
    except operating_service.OperatingError as exc:
        raise _bad_request(exc) from exc


@router.delete(
    "/acquisitions/{acquisition_id}/operating/unit-group/{unit_group_id}",
    response_model=OperatingDoc,
)
async def remove_unit_group(
    acquisition_id: str,
    unit_group_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> OperatingDoc:
    """Remove a unit group (drivers recompute from the rest)."""
    try:
        return await operating_service.remove_unit_group(
            session, acquisition_id, unit_group_id, actor=principal.user_id
        )
    except operating_service.OperatingError as exc:
        raise _bad_request(exc) from exc

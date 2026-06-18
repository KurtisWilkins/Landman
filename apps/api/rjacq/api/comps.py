"""Comp intelligence endpoints (§9, §5.6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..comps import service
from ..comps.enrichment import build_enricher
from ..comps.service import CompError
from ..core.auth import Principal, get_current_principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..models.acquisitions import Acquisition
from ..schemas.comps import CompManualAdd, CompOut, CompSet

router = APIRouter(tags=["comps"])


@router.get("/acquisitions/{acquisition_id}/comps", response_model=CompSet)
async def get_comps(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> CompSet:
    """Comp set + visualization data (rate×sentiment / rate×amenities)."""
    return await service.build_comp_set(session, acquisition_id)


@router.post(
    "/acquisitions/{acquisition_id}/comps",
    response_model=CompOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_comp(
    acquisition_id: str,
    body: CompManualAdd,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> CompOut:
    """Manual competitor add by URL or direct fields → scrape/enrich."""
    acquisition = await session.get(Acquisition, acquisition_id)
    acquisition_lat = (
        float(acquisition.lat) if acquisition and acquisition.lat is not None else None
    )
    acquisition_lng = (
        float(acquisition.lng) if acquisition and acquisition.lng is not None else None
    )
    try:
        comp = await service.add_manual(
            session,
            acquisition_id=acquisition_id,
            url=body.url,
            name=body.name,
            lat=body.lat,
            lng=body.lng,
            avg_rate=body.avg_rate,
            acquisition_lat=acquisition_lat,
            acquisition_lng=acquisition_lng,
            enricher=build_enricher(),
        )
    except CompError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    await session.commit()
    return comp

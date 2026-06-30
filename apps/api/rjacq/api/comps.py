"""Comp intelligence endpoints (§9, §5.6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..comps import service
from ..comps.enrichment import build_enricher
from ..comps.geocode import build_geocoder
from ..comps.service import CompError
from ..comps.sources import build_sources
from ..core.auth import Principal, get_current_principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..models.acquisitions import Acquisition
from ..schemas.comps import CompDiscoverResult, CompManualAdd, CompOut, CompSet

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
    "/acquisitions/{acquisition_id}/comps/discover",
    response_model=CompDiscoverResult,
)
async def discover_comps(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> CompDiscoverResult:
    """Find competitors within 50 miles of the acquisition's (OM) address: geocode the address,
    then search every enabled source and persist the matches. Runs **synchronously** — the work is
    bounded (OSM is a single radius query) and the source HTTP runs off the event loop — so it does
    not depend on the Redis/worker queue. Returns the geocode + the number of competitors found."""
    geocoder = build_geocoder()
    try:
        lat, lng = await service.ensure_location(session, acquisition_id, geocoder=geocoder)
        count = await service.discover_comps(
            session,
            acquisition_id=acquisition_id,
            acquisition_lat=lat,
            acquisition_lng=lng,
            sources=build_sources(),
            enricher=build_enricher(),
        )
    except CompError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    await session.commit()
    return CompDiscoverResult(status="complete", lat=lat, lng=lng, count=count)


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

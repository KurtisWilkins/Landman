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
from ..models.deals import Deal
from ..schemas.comps import CompManualAdd, CompOut, CompSet

router = APIRouter(tags=["comps"])


@router.get("/deals/{deal_id}/comps", response_model=CompSet)
async def get_comps(
    deal_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> CompSet:
    """Comp set + visualization data (rate×sentiment / rate×amenities)."""
    return await service.build_comp_set(session, deal_id)


@router.post("/deals/{deal_id}/comps", response_model=CompOut, status_code=status.HTTP_201_CREATED)
async def add_comp(
    deal_id: str,
    body: CompManualAdd,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.DEAL_WRITE)),
) -> CompOut:
    """Manual competitor add by URL or direct fields → scrape/enrich."""
    deal = await session.get(Deal, deal_id)
    deal_lat = float(deal.lat) if deal and deal.lat is not None else None
    deal_lng = float(deal.lng) if deal and deal.lng is not None else None
    try:
        comp = await service.add_manual(
            session,
            deal_id=deal_id,
            url=body.url,
            name=body.name,
            lat=body.lat,
            lng=body.lng,
            avg_rate=body.avg_rate,
            deal_lat=deal_lat,
            deal_lng=deal_lng,
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

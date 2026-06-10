"""Comp intelligence endpoints (§9, §5.6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from ..core.auth import Principal, get_current_principal
from ..core.rbac import Capability, require
from ..schemas.comps import CompManualAdd, CompOut, CompSet
from ._stub import not_implemented

router = APIRouter(tags=["comps"])


@router.get("/deals/{deal_id}/comps", response_model=CompSet)
async def get_comps(
    deal_id: str,
    _principal: Principal = Depends(get_current_principal),
) -> CompSet:
    """Comp set + visualization data (rate×sentiment / rate×amenities)."""
    not_implemented("GET /deals/{id}/comps", phase="Phase 3 (comps)")


@router.post("/deals/{deal_id}/comps", response_model=CompOut, status_code=status.HTTP_201_CREATED)
async def add_comp(
    deal_id: str,
    _body: CompManualAdd,
    _principal: Principal = Depends(require(Capability.DEAL_WRITE)),
) -> CompOut:
    """Manual competitor add by URL or direct fields → scrape/enrich."""
    not_implemented("POST /deals/{id}/comps", phase="Phase 3 (comps)")

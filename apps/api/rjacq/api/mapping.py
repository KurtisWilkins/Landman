"""GL mapping review endpoints (§9, §5.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.auth import Principal, get_current_principal
from ..core.rbac import Capability, require
from ..schemas.financials import MappingConfirm, MappingReview
from ._stub import not_implemented

router = APIRouter(tags=["mapping"])


@router.get("/deals/{deal_id}/mapping", response_model=MappingReview)
async def get_mapping_queue(
    deal_id: str,
    _principal: Principal = Depends(get_current_principal),
) -> MappingReview:
    """Mapping queue for human review (proposals + candidate shortlist)."""
    not_implemented("GET /deals/{id}/mapping", phase="Phase 1 (mapping)")


@router.post("/deals/{deal_id}/mapping/confirm", response_model=MappingReview)
async def confirm_mapping(
    deal_id: str,
    _body: MappingConfirm,
    _principal: Principal = Depends(require(Capability.MAPPING_CONFIRM)),
) -> MappingReview:
    """Human accepts a mapping → writes a learned mapping for reuse (§5.3.5)."""
    not_implemented("POST /deals/{id}/mapping/confirm", phase="Phase 1 (mapping)")

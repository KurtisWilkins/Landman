"""GL mapping review endpoints (§9, §5.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import Principal, get_current_principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..mapping import service
from ..mapping.providers import build_embedder
from ..mapping.service import MappingError
from ..schemas.financials import MappingConfirm, MappingReview

router = APIRouter(tags=["mapping"])


@router.get("/acquisitions/{acquisition_id}/mapping", response_model=MappingReview)
async def get_mapping_queue(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> MappingReview:
    """Mapping queue for human review (proposals + candidate shortlist)."""
    return await service.build_review(session, acquisition_id, embedder=build_embedder())


@router.post("/acquisitions/{acquisition_id}/mapping/confirm", response_model=MappingReview)
async def confirm_mapping(
    acquisition_id: str,
    body: MappingConfirm,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.MAPPING_CONFIRM)),
) -> MappingReview:
    """Human accepts a mapping → writes a learned mapping for reuse (§5.3.5)."""
    try:
        await service.confirm(
            session,
            line_id=body.line_id,
            account_code=body.account_code,
            account_level=body.account_level.value,
            noi_placement=body.noi_placement.value,
            learn=body.learn,
            confirmed_by=principal.user_id,
        )
    except MappingError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    await session.commit()
    return await service.build_review(session, acquisition_id, embedder=build_embedder())

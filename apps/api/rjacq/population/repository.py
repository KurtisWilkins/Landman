"""Repository for population rings (DB access only)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.market import PopulationRing


def _new_id() -> str:
    return f"pr_{uuid.uuid4().hex[:16]}"


async def list_rings(session: AsyncSession, acquisition_id: str) -> Sequence[PopulationRing]:
    stmt = (
        select(PopulationRing)
        .where(PopulationRing.acquisition_id == acquisition_id)
        .order_by(PopulationRing.radius_mi)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_ring(
    session: AsyncSession, acquisition_id: str, radius_mi: int
) -> PopulationRing | None:
    stmt = select(PopulationRing).where(
        PopulationRing.acquisition_id == acquisition_id, PopulationRing.radius_mi == radius_mi
    )
    return (await session.execute(stmt)).scalars().first()


async def upsert_ring(session: AsyncSession, acquisition_id: str, radius_mi: int) -> PopulationRing:
    ring = await get_ring(session, acquisition_id, radius_mi)
    if ring is None:
        ring = PopulationRing(ring_id=_new_id(), acquisition_id=acquisition_id, radius_mi=radius_mi)
        session.add(ring)
        await session.flush()
    return ring

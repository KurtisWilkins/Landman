"""Repository for comps (DB access only)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.comps import Comp
from .enrichment import Enrichment


def _new_id() -> str:
    return f"cp_{uuid.uuid4().hex[:16]}"


async def insert_comp(
    session: AsyncSession,
    acquisition_id: str,
    *,
    name: str,
    lat: float | None,
    lng: float | None,
    distance_mi: Decimal | None,
    avg_rate: Decimal | None,
    source: str,
    is_manual: bool,
    enrichment: Enrichment | None,
    raw: dict[str, Any] | None,
) -> Comp:
    e = enrichment or Enrichment()
    comp = Comp(
        comp_id=_new_id(),
        acquisition_id=acquisition_id,
        name=name,
        lat=lat,
        lng=lng,
        distance_mi=distance_mi,
        avg_rate=avg_rate,
        sentiment_score=e.sentiment_score,
        amenity_score=e.amenity_score,
        ai_summary=e.ai_summary,
        best_snippet=e.best_snippet,
        worst_snippet=e.worst_snippet,
        source=source,
        is_manual=is_manual,
        scraped_at=datetime.now(UTC),
        raw_payload=raw,
    )
    session.add(comp)
    await session.flush()
    return comp


async def list_comps(session: AsyncSession, acquisition_id: str) -> Sequence[Comp]:
    stmt = select(Comp).where(Comp.acquisition_id == acquisition_id).order_by(Comp.distance_mi)
    return (await session.execute(stmt)).scalars().all()


async def assign_amenity_ranks(session: AsyncSession, acquisition_id: str) -> None:
    """Rank comps 1..N by amenity_score (desc); comps without a score are left unranked."""
    comps = [c for c in await list_comps(session, acquisition_id) if c.amenity_score is not None]
    for rank, comp in enumerate(sorted(comps, key=lambda c: c.amenity_score or 0, reverse=True), 1):
        comp.amenity_rank = rank
    await session.flush()

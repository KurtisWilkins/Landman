"""Comp intelligence service (design doc §5.6): discover within radius, enrich, persist;
manual add; assemble the comp set + visualization data.

Per-source success/failure is logged; one failing source never blocks the others. AI
enrichment is applied only when configured (C-20).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..models.comps import Comp
from ..schemas.comps import (
    CompOut,
    CompScatterPoint,
    CompSet,
    CompVisualization,
)
from . import repository as repo
from .distance import COMP_RADIUS_MILES, haversine_miles, within_radius
from .enrichment import Enricher
from .sources import CompSource, RawComp

log = get_logger("comps")


class CompError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def discover_comps(
    session: AsyncSession,
    *,
    deal_id: str,
    deal_lat: float,
    deal_lng: float,
    sources: Sequence[CompSource],
    enricher: Enricher | None,
    radius_miles: float = COMP_RADIUS_MILES,
) -> int:
    """Discover comps within the radius across all sources; enrich + persist. Returns count."""
    inserted = 0
    for source in sources:
        try:
            found = source.discover(deal_lat, deal_lng, radius_miles)
        except Exception:  # one bad source never blocks the rest (§12 resilience)
            log.warning("comps.source_failed", source=source.name)
            continue
        kept = [
            c
            for c in found
            if c.lat is not None
            and c.lng is not None
            and within_radius(deal_lat, deal_lng, c.lat, c.lng, radius_miles)
        ]
        for raw in kept:
            await _persist(session, deal_id, raw, deal_lat, deal_lng, enricher, is_manual=False)
            inserted += 1
        log.info("comps.source_done", source=source.name, found=len(found), kept=len(kept))
    await repo.assign_amenity_ranks(session, deal_id)
    return inserted


async def add_manual(
    session: AsyncSession,
    *,
    deal_id: str,
    url: str | None,
    name: str | None,
    lat: float | None,
    lng: float | None,
    avg_rate: Decimal | None,
    deal_lat: float | None,
    deal_lng: float | None,
    enricher: Enricher | None,
) -> CompOut:
    """Operator adds a competitor by URL or direct fields; system enriches it (§5.6)."""
    if not url and not name:
        raise CompError("invalid_manual_add", "Provide a url or a name.")
    raw = RawComp(
        name=name or (url or "Manual comp"),
        lat=lat,
        lng=lng,
        avg_rate=avg_rate,
        source="manual",
        raw={"url": url} if url else {},
    )
    comp = await _persist(session, deal_id, raw, deal_lat, deal_lng, enricher, is_manual=True)
    await repo.assign_amenity_ranks(session, deal_id)
    return CompOut.model_validate(comp)


async def _persist(
    session: AsyncSession,
    deal_id: str,
    raw: RawComp,
    deal_lat: float | None,
    deal_lng: float | None,
    enricher: Enricher | None,
    *,
    is_manual: bool,
) -> Comp:
    distance = None
    if (
        deal_lat is not None
        and deal_lng is not None
        and raw.lat is not None
        and raw.lng is not None
    ):
        distance = Decimal(str(round(haversine_miles(deal_lat, deal_lng, raw.lat, raw.lng), 2)))
    enrichment = enricher.enrich(raw) if enricher is not None else None
    return await repo.insert_comp(
        session,
        deal_id,
        name=raw.name,
        lat=raw.lat,
        lng=raw.lng,
        distance_mi=distance,
        avg_rate=raw.avg_rate,
        source=raw.source,
        is_manual=is_manual,
        enrichment=enrichment,
        raw=raw.raw,
    )


async def build_comp_set(session: AsyncSession, deal_id: str) -> CompSet:
    """Assemble the comp set + visualization (rate×sentiment / rate×amenities scatter)."""
    comps = await repo.list_comps(session, deal_id)
    points = [
        CompScatterPoint(
            comp_id=c.comp_id,
            name=c.name,
            avg_rate=c.avg_rate,
            sentiment_score=c.sentiment_score,
            amenity_score=c.amenity_score,
            is_target=False,
        )
        for c in comps
    ]
    return CompSet(
        comps=[CompOut.model_validate(c) for c in comps],
        visualization=CompVisualization(points=points),
    )

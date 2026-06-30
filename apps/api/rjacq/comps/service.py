"""Comp intelligence service (design doc §5.6): discover within radius, enrich, persist;
manual add; assemble the comp set + visualization data.

Per-source success/failure is logged; one failing source never blocks the others. AI
enrichment is applied only when configured (C-20).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..models.acquisitions import Acquisition
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
from .geocode import Geocoder, address_query
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
    acquisition_id: str,
    acquisition_lat: float,
    acquisition_lng: float,
    sources: Sequence[CompSource],
    enricher: Enricher | None,
    radius_miles: float = COMP_RADIUS_MILES,
) -> int:
    """Discover comps within the radius across all sources; enrich + persist. Returns count.

    Refresh-replace: the acquisition's prior auto-discovered comps are cleared first (manual adds
    are kept), so re-running discovery is idempotent rather than accumulating duplicates."""
    await repo.delete_discovered(session, acquisition_id)
    inserted = 0
    for source in sources:
        try:
            # Sources do blocking HTTP (httpx); run them off the event loop so the synchronous
            # discovery path doesn't stall the API's loop (and it's harmless in the worker).
            found = await asyncio.to_thread(
                source.discover, acquisition_lat, acquisition_lng, radius_miles
            )
        except Exception:  # one bad source never blocks the rest (§12 resilience)
            log.warning("comps.source_failed", source=source.name)
            continue
        kept = [
            c
            for c in found
            if c.lat is not None
            and c.lng is not None
            and within_radius(acquisition_lat, acquisition_lng, c.lat, c.lng, radius_miles)
        ]
        for raw in kept:
            await _persist(
                session,
                acquisition_id,
                raw,
                acquisition_lat,
                acquisition_lng,
                enricher,
                is_manual=False,
            )
            inserted += 1
        log.info("comps.source_done", source=source.name, found=len(found), kept=len(kept))
    await repo.assign_amenity_ranks(session, acquisition_id)
    return inserted


async def ensure_location(
    session: AsyncSession, acquisition_id: str, *, geocoder: Geocoder | None
) -> tuple[float, float]:
    """Return the acquisition's (lat, lng), geocoding the OM address on first use and persisting it
    (so the map + population rings can reuse it). Raises ``CompError`` if there is no address we can
    locate — never guesses a location."""
    acquisition = await session.get(Acquisition, acquisition_id)
    if acquisition is None:
        raise CompError("not_found", "No such acquisition.")
    if acquisition.lat is not None and acquisition.lng is not None:
        return float(acquisition.lat), float(acquisition.lng)
    query = address_query(
        acquisition.address_line1, acquisition.city, acquisition.state, acquisition.zip
    )
    if not query:
        raise CompError("no_address", "This acquisition has no address to locate.")
    result = geocoder.geocode(query) if geocoder is not None else None
    if result is None:
        raise CompError("geocode_failed", f"Couldn't locate the address: {query}.")
    acquisition.lat = result.lat
    acquisition.lng = result.lng
    await session.flush()
    log.info("comps.geocoded", acquisition_id=acquisition_id, provider=result.provider)
    return result.lat, result.lng


async def discover_for_acquisition(
    session: AsyncSession,
    acquisition_id: str,
    *,
    sources: Sequence[CompSource],
    enricher: Enricher | None,
    geocoder: Geocoder | None,
    radius_miles: float = COMP_RADIUS_MILES,
) -> int:
    """End-to-end discovery from the acquisition's OM address: geocode → discover within radius."""
    lat, lng = await ensure_location(session, acquisition_id, geocoder=geocoder)
    return await discover_comps(
        session,
        acquisition_id=acquisition_id,
        acquisition_lat=lat,
        acquisition_lng=lng,
        sources=sources,
        enricher=enricher,
        radius_miles=radius_miles,
    )


async def add_manual(
    session: AsyncSession,
    *,
    acquisition_id: str,
    url: str | None,
    name: str | None,
    lat: float | None,
    lng: float | None,
    avg_rate: Decimal | None,
    acquisition_lat: float | None,
    acquisition_lng: float | None,
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
    comp = await _persist(
        session, acquisition_id, raw, acquisition_lat, acquisition_lng, enricher, is_manual=True
    )
    await repo.assign_amenity_ranks(session, acquisition_id)
    return CompOut.model_validate(comp)


async def _persist(
    session: AsyncSession,
    acquisition_id: str,
    raw: RawComp,
    acquisition_lat: float | None,
    acquisition_lng: float | None,
    enricher: Enricher | None,
    *,
    is_manual: bool,
) -> Comp:
    distance = None
    if (
        acquisition_lat is not None
        and acquisition_lng is not None
        and raw.lat is not None
        and raw.lng is not None
    ):
        distance = Decimal(
            str(round(haversine_miles(acquisition_lat, acquisition_lng, raw.lat, raw.lng), 2))
        )
    enrichment = enricher.enrich(raw) if enricher is not None else None
    return await repo.insert_comp(
        session,
        acquisition_id,
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


async def build_comp_set(session: AsyncSession, acquisition_id: str) -> CompSet:
    """Assemble the comp set + visualization (rate×sentiment / rate×amenities scatter)."""
    comps = await repo.list_comps(session, acquisition_id)
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

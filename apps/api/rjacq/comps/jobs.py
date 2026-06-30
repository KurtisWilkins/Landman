"""Background comp-discovery job (design doc §5.6).

Finding competitors within the 50-mile radius is a burst of external HTTP (geocode + one or more
source APIs), so it runs off the request path: the endpoint geocodes + enqueues, the worker does
the discovery. Degrades gracefully — OSM is always available (no key); Google joins when keyed;
the niche-site scrapers stay off until D-22 clears. Nothing is auto-accepted into underwriting.
"""

from __future__ import annotations

from typing import Any

from ..core import db as core_db
from ..core.logging import get_logger
from . import service
from .enrichment import build_enricher
from .geocode import build_geocoder
from .sources import build_sources

log = get_logger("comps")


async def discover_acquisition_comps(ctx: dict[str, Any], acquisition_id: str) -> int:
    """Geocode the acquisition's address (if needed) and discover comps within 50 miles across all
    enabled sources. Returns the number of comps inserted."""
    async with core_db.SessionFactory() as session:
        try:
            count = await service.discover_for_acquisition(
                session,
                acquisition_id,
                sources=build_sources(),
                enricher=build_enricher(),
                geocoder=build_geocoder(),
            )
        except service.CompError as exc:
            log.warning("comps.discover_skipped", acquisition_id=acquisition_id, reason=exc.code)
            await session.rollback()
            return 0
        await session.commit()
    log.info("comps.discovered", acquisition_id=acquisition_id, count=count)
    return count

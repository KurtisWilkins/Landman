"""Population-rings service (design doc §5.5): auto-pull on property entry, manual override,
and assemble the rings for the deal document. Baseline (provider) + override + author + note
are kept side by side (provenance); an override is never clobbered by a refresh.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..models.market import RING_RADII_MILES
from ..schemas.market import PopulationRingOut, PopulationRingsDoc
from . import repository as repo
from .provider import PopulationProvider

log = get_logger("population")


class PopulationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def refresh_rings(
    session: AsyncSession,
    deal_id: str,
    *,
    lat: float | None,
    lng: float | None,
    provider: PopulationProvider | None,
) -> int:
    """Auto-pull baseline ring populations. No-op (0) when there's no geocode or no provider
    (graceful — rings stay empty/operator-entered, never fabricated). Overrides preserved."""
    if lat is None or lng is None or provider is None:
        log.info("population.refresh_skipped", deal_id=deal_id, has_provider=provider is not None)
        return 0
    estimates = {e.radius_mi: e for e in provider.estimate_rings(lat, lng, RING_RADII_MILES)}
    updated = 0
    for radius in RING_RADII_MILES:
        est = estimates.get(radius)
        if est is None:
            continue
        ring = await repo.upsert_ring(session, deal_id, radius)
        ring.baseline_population = est.population  # refresh baseline; override untouched
        ring.source = provider.name
        ring.as_of = est.as_of
        updated += 1
    await session.flush()
    log.info("population.refreshed", deal_id=deal_id, rings=updated, source=provider.name)
    return updated


async def override_ring(
    session: AsyncSession,
    deal_id: str,
    *,
    radius_mi: int,
    population: int,
    note: str | None,
    author: str,
) -> None:
    """Record an operator override for one ring (baseline retained — provenance)."""
    if radius_mi not in RING_RADII_MILES:
        raise PopulationError("invalid_radius", f"radius_mi must be one of {RING_RADII_MILES}.")
    ring = await repo.upsert_ring(session, deal_id, radius_mi)
    ring.override_population = population
    ring.is_override = True
    ring.overridden_by = author
    ring.note = note
    await session.flush()
    log.info("population.overridden", deal_id=deal_id, radius_mi=radius_mi, by=author)


async def get_rings(session: AsyncSession, deal_id: str) -> PopulationRingsDoc:
    rings = await repo.list_rings(session, deal_id)
    out = [
        PopulationRingOut(
            radius_mi=r.radius_mi,
            population=(r.override_population if r.is_override else r.baseline_population),
            baseline_population=r.baseline_population,
            is_override=r.is_override,
            overridden_by=r.overridden_by,
            note=r.note,
            source=r.source,
            as_of=r.as_of,
        )
        for r in rings
    ]
    return PopulationRingsDoc(rings=out)

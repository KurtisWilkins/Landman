"""Demographics provider seam for population rings (design doc §5.5).

``estimate_rings`` returns population by radius for a lat/lng. ADR-0009 selects **US Census
ACS** (county-grain) as the provider; ``build_population_provider`` returns a configured
provider when ``POPULATION_PROVIDER``/key are set, else None — so we never fabricate
population figures (rings stay operator-entered until a provider is wired).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from ..core.config import settings
from ..core.logging import get_logger

log = get_logger("population.provider")


@dataclass(frozen=True)
class RingEstimate:
    radius_mi: int
    population: int
    as_of: date | None = None


@runtime_checkable
class PopulationProvider(Protocol):
    name: str

    def estimate_rings(
        self, lat: float, lng: float, radii: Sequence[int]
    ) -> list[RingEstimate]: ...


def build_population_provider() -> PopulationProvider | None:
    """Return the configured demographics provider, or None when unconfigured.

    Per ADR-0009 the wired provider is US Census ACS (``POPULATION_PROVIDER=census``). With no
    provider configured, rings stay manual — populations are never fabricated.
    """
    provider = settings.population_provider
    if not (provider and settings.population_provider_api_key):
        return None
    if provider.lower() == "census":
        from .census import CensusACSProvider

        return CensusACSProvider(
            settings.population_provider_api_key, year=settings.census_acs_year
        )
    # An unrecognized provider name is configured: fail safe to manual entry, don't guess.
    log.warning("population.unknown_provider", provider=provider)
    return None

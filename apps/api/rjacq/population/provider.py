"""Demographics provider seam for population rings (design doc §5.5).

``estimate_rings`` returns population by radius for a lat/lng. The provider + key is an
unresolved decision (ADR-0009: Census vs Esri vs other); ``build_population_provider``
returns None until configured, so we never fabricate population figures.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from ..core.config import settings


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
    """Return a configured demographics provider, or None until ADR-0009 is resolved.

    TODO(decision: ADR-0009): pick the provider (e.g. US Census ACS / Esri) and wire its
    HTTP client here, mapping radius-band population to RingEstimate with the estimate vintage.
    """
    if not (settings.population_provider and settings.population_provider_api_key):
        return None
    return None

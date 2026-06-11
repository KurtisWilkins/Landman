"""Comp source connectors behind one interface (design doc §5.6).

Official APIs (Google Places, Yelp, TripAdvisor) and — only behind a config flag — niche-site
scrapers (Campendium/Camp Media, The Dirt). API-vs-scraping per source is unresolved
(§14 D-22): scrapers are NOT built unless ``scrapers_enabled`` is set, and sites pending
legal review stay off. The build returns only the configured/permitted sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from ..core.config import settings


@dataclass(frozen=True)
class RawComp:
    name: str
    lat: float | None
    lng: float | None
    avg_rate: Decimal | None
    source: str
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CompSource(Protocol):
    name: str

    def discover(self, lat: float, lng: float, radius_miles: float) -> list[RawComp]: ...


class _ApiSource:
    """Base for official-API connectors. The concrete API calls land with the per-source
    contract (D-22); until then a configured source yields nothing (graceful, not a guess)."""

    name = "api"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def discover(self, lat: float, lng: float, radius_miles: float) -> list[RawComp]:
        # TODO(decision: §14 D-22): call the official API; map results to RawComp + raw_payload.
        return []


class GooglePlacesSource(_ApiSource):
    name = "google"


class YelpSource(_ApiSource):
    name = "yelp"


class TripAdvisorSource(_ApiSource):
    name = "tripadvisor"


def build_sources() -> list[CompSource]:
    """Return enabled comp sources. Official APIs require their key; scrapers require the
    ``scrapers_enabled`` flag (off by default; D-22 ToS/legal review)."""
    sources: list[CompSource] = []
    if settings.google_places_api_key:
        sources.append(GooglePlacesSource(settings.google_places_api_key))
    if settings.yelp_api_key:
        sources.append(YelpSource(settings.yelp_api_key))
    if settings.tripadvisor_api_key:
        sources.append(TripAdvisorSource(settings.tripadvisor_api_key))
    # Niche-site scrapers (Campendium/Camp Media, The Dirt) stay behind the flag until
    # D-22 clears them; not constructed here while disabled.
    if settings.scrapers_enabled:
        # TODO(decision: §14 D-22): add Playwright scrapers once ToS/legal review clears them.
        pass
    return sources

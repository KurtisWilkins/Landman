"""Address → (lat, lng) geocoding seam (design doc §5.6).

OMs give a street address, not coordinates, so the comp-radius search needs to geocode first.
Mirrors the population-provider pattern: a provider chain tried in order, returning the first hit;
it never fabricates a location (a miss returns ``None`` and the caller surfaces "couldn't locate").

Providers:
- **Google Geocoding** (when ``google_places_api_key`` is set) — most accurate; same key as Places.
- **Nominatim / OpenStreetMap** — free, no key; always available as the fallback. Its usage policy
  requires a UA identifying the app (``settings.osm_user_agent``) and at most ~1 req/s, which the
  one-off-per-acquisition discovery flow respects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx

from ..core.config import settings
from ..core.logging import get_logger

log = get_logger("comps.geocode")
_HTTP_TIMEOUT = 15.0


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lng: float
    provider: str


def address_query(
    line1: str | None, city: str | None, state: str | None, zip_code: str | None
) -> str:
    """Join the stored address parts into a single geocoder query (skips blanks)."""
    return ", ".join(p.strip() for p in (line1, city, state, zip_code) if p and p.strip())


@runtime_checkable
class Geocoder(Protocol):
    name: str

    def geocode(self, query: str) -> GeocodeResult | None: ...


class NominatimGeocoder:
    name = "nominatim"

    def __init__(self, user_agent: str) -> None:
        self._ua = user_agent

    def geocode(self, query: str) -> GeocodeResult | None:
        resp = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": self._ua},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return None
        return GeocodeResult(float(rows[0]["lat"]), float(rows[0]["lon"]), self.name)


class GoogleGeocoder:
    name = "google"

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def geocode(self, query: str) -> GeocodeResult | None:
        resp = httpx.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": query, "key": self._key},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results") or []
        if body.get("status") != "OK" or not results:
            return None
        loc = results[0]["geometry"]["location"]
        return GeocodeResult(float(loc["lat"]), float(loc["lng"]), self.name)


class ChainGeocoder:
    """Try each provider in order; the first that resolves wins. A provider error is logged and
    skipped so a single outage never blocks the rest."""

    name = "chain"

    def __init__(self, providers: list[Geocoder]) -> None:
        self._providers = providers

    def geocode(self, query: str) -> GeocodeResult | None:
        for provider in self._providers:
            try:
                hit = provider.geocode(query)
            except Exception as exc:  # network / parse / rate-limit
                log.warning(
                    "comps.geocode_failed", provider=provider.name, error=type(exc).__name__
                )
                continue
            if hit is not None:
                return hit
        return None


def build_geocoder() -> Geocoder:
    """Google first (if keyed), then the always-available free Nominatim fallback."""
    providers: list[Geocoder] = []
    if settings.google_places_api_key:
        providers.append(GoogleGeocoder(settings.google_places_api_key))
    providers.append(NominatimGeocoder(settings.osm_user_agent))
    return ChainGeocoder(providers)

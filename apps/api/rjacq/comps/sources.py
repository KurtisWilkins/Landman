"""Comp source connectors behind one interface (design doc §5.6).

The competitive set for an RV-resort acquisition: **RV parks, campgrounds, RV resorts**, plus
(per the broadened scope) **glamping sites and marinas** with overnight stay. Each source maps its
raw results to ``RawComp``; the service applies the 50-mile haversine filter, so a source may
slightly over-fetch.

Sources:
- **OpenStreetMap / Overpass** (`osm`): free, no key, always on. A single ``around:`` query covers
  the full 50-mile radius. The workhorse.
- **Google Places** (`google`): richer (ratings), live when ``google_places_api_key`` is set.
  Nearby Search caps at ~31 mi/request, so we tile the disc and dedupe by ``place_id``.
- **Niche RV directories** (Campendium / RV LIFE): the richest rate/amenity data, but **scraped** —
  kept behind ``scrapers_enabled`` until a per-site ToS/legal review clears D-22. Inert until then.

Per-source failures are isolated by the service (one bad source never blocks the others).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

import httpx

from ..core.config import settings
from ..core.logging import get_logger

log = get_logger("comps.sources")
_HTTP_TIMEOUT = 30.0
_METERS_PER_MILE = 1609.344
_MILES_PER_DEG_LAT = 69.0

# OSM tags that denote an overnight-stay competitor (incl. the broadened glamping + marina scope).
_OSM_FILTERS = (
    '["tourism"="caravan_site"]',  # RV park
    '["tourism"="camp_site"]',  # campground (glamping is camp_site + tents=… / glamping=…)
    '["leisure"="marina"]',  # marina (overnight slips)
)
# Google Place keywords for the same set (types rv_park/campground + resort/glamping/marina).
_GOOGLE_KEYWORDS = ("RV park", "RV resort", "campground", "glamping", "marina")


@dataclass(frozen=True)
class RawComp:
    name: str
    lat: float | None
    lng: float | None
    avg_rate: Decimal | None
    source: str
    external_ref: str | None = None  # provider id (place_id / osm id) for dedupe
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CompSource(Protocol):
    name: str

    def discover(self, lat: float, lng: float, radius_miles: float) -> list[RawComp]: ...


# ── geometry (pure, unit-tested) ─────────────────────────────────────────────


def tile_centers(
    lat: float, lng: float, radius_miles: float, tile_radius_miles: float = 30.0
) -> list[tuple[float, float]]:
    """Cover a ``radius_miles`` disc with circular tiles of ``tile_radius_miles`` (a provider's
    per-request cap), leaving no interior gaps: the center plus concentric rings spaced one tile
    radius apart, each ring carrying enough points that neighbours are ≤ one tile radius apart. The
    caller still haversine-filters, so edge over-coverage is harmless."""
    centers = [(lat, lng)]
    cos_lat = max(0.01, math.cos(math.radians(lat)))
    d = tile_radius_miles
    while d - tile_radius_miles < radius_miles:
        n = max(6, math.ceil(2 * math.pi * d / tile_radius_miles))
        for k in range(n):
            ang = 2 * math.pi * k / n
            dy = d * math.cos(ang)
            dx = d * math.sin(ang)
            centers.append(
                (
                    lat + dy / _MILES_PER_DEG_LAT,
                    lng + dx / (_MILES_PER_DEG_LAT * cos_lat),
                )
            )
        d += tile_radius_miles
    return centers


# ── OpenStreetMap / Overpass (free, always on) ───────────────────────────────


def build_overpass_query(lat: float, lng: float, radius_miles: float) -> str:
    """An Overpass QL query for overnight-stay competitors within the radius (single request)."""
    r = int(round(radius_miles * _METERS_PER_MILE))
    clauses = "".join(f"  nwr{f}(around:{r},{lat:.6f},{lng:.6f});\n" for f in _OSM_FILTERS)
    return f"[out:json][timeout:25];\n(\n{clauses});\nout center tags;"


def parse_overpass(data: dict[str, Any]) -> list[RawComp]:
    """Map an Overpass JSON response to named comps (ways/relations carry a ``center``)."""
    out: list[RawComp] = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue  # an unnamed pitch/site isn't a usable competitor
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        out.append(
            RawComp(
                name=name,
                lat=float(lat),
                lng=float(lon),
                avg_rate=None,
                source="osm",
                external_ref=f"{el.get('type')}/{el.get('id')}",
                raw={"tags": tags, "osm_type": el.get("type"), "osm_id": el.get("id")},
            )
        )
    return out


class OpenStreetMapSource:
    name = "osm"

    def discover(self, lat: float, lng: float, radius_miles: float) -> list[RawComp]:
        query = build_overpass_query(lat, lng, radius_miles)
        resp = httpx.post(settings.overpass_url, data={"data": query}, timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        return parse_overpass(resp.json())


# ── Google Places (richer; live when keyed) ──────────────────────────────────


def parse_google_places(data: dict[str, Any]) -> list[RawComp]:
    """Map one Google Places Nearby/Text Search page to comps."""
    out: list[RawComp] = []
    for r in data.get("results", []):
        loc = (r.get("geometry") or {}).get("location") or {}
        if "lat" not in loc or "lng" not in loc:
            continue
        out.append(
            RawComp(
                name=r.get("name", "Unknown"),
                lat=float(loc["lat"]),
                lng=float(loc["lng"]),
                avg_rate=None,  # price_level (0–4) isn't a nightly $; left for enrichment
                source="google",
                external_ref=r.get("place_id"),
                raw={
                    "place_id": r.get("place_id"),
                    "rating": r.get("rating"),
                    "user_ratings_total": r.get("user_ratings_total"),
                    "price_level": r.get("price_level"),
                    "types": r.get("types"),
                    "vicinity": r.get("vicinity") or r.get("formatted_address"),
                },
            )
        )
    return out


class GooglePlacesSource:
    name = "google"

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def _fetch(self, lat: float, lng: float, keyword: str, radius_m: int) -> dict[str, Any]:
        resp = httpx.get(
            "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
            params={
                "location": f"{lat},{lng}",
                "radius": radius_m,
                "keyword": keyword,
                "key": self._key,
            },
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        return body

    def discover(self, lat: float, lng: float, radius_miles: float) -> list[RawComp]:
        # Nearby Search caps at 50 km (~31 mi); tile the disc at 30 mi and dedupe by place_id.
        tile_r = 30.0
        radius_m = min(50_000, int(round(tile_r * _METERS_PER_MILE)))
        seen: set[str] = set()
        comps: list[RawComp] = []
        for clat, clng in tile_centers(lat, lng, radius_miles, tile_radius_miles=tile_r):
            for keyword in _GOOGLE_KEYWORDS:
                try:
                    page = self._fetch(clat, clng, keyword, radius_m)
                except Exception as exc:
                    log.warning("comps.google_tile_failed", error=type(exc).__name__)
                    continue
                for comp in parse_google_places(page):
                    ref = comp.external_ref or comp.name
                    if ref in seen:
                        continue
                    seen.add(ref)
                    comps.append(comp)
        return comps


# ── Niche RV directories (scraped — gated behind D-22) ────────────────────────


class _ScraperSource:
    """Campendium / RV LIFE / The Dirt carry the richest rate + amenity data, but scraping them is
    gated by D-22 (per-site ToS / legal review). Wired into the framework but inert until
    ``scrapers_enabled`` is set AND the per-site review clears — never scrapes silently."""

    name = "scraper"

    def discover(self, lat: float, lng: float, radius_miles: float) -> list[RawComp]:
        log.info("comps.scraper_pending_review", source=self.name)
        # TODO(decision: §14 D-22): implement once the per-site ToS/legal review clears the site.
        return []


class CampendiumSource(_ScraperSource):
    name = "campendium"


class RvLifeSource(_ScraperSource):
    name = "rvlife"


def build_sources() -> list[CompSource]:
    """Enabled comp sources: OSM is always on (free); Google when keyed; the niche-site scrapers
    only when ``scrapers_enabled`` is set (D-22 ToS/legal review)."""
    sources: list[CompSource] = [OpenStreetMapSource()]
    if settings.google_places_api_key:
        sources.append(GooglePlacesSource(settings.google_places_api_key))
    if settings.scrapers_enabled:
        sources.extend([CampendiumSource(), RvLifeSource()])
    return sources

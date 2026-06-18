"""US Census ACS demographics provider for population rings (ADR-0009).

Estimates population within each ring radius by aggregating **county-level** ACS 5-year
population (table ``B01003``) for every county whose internal-point centroid falls within the
radius of the acquisition. County centroids are bundled (US Census 2023 Gazetteer, ``data/``);
population is pulled live from the free Census Data API in a single nationwide call.

This is a coarse, county-grain estimate by design — it travels with its vintage (``as_of``)
and ``source`` for provenance and is always operator-overridable. A ring that captures no
county centroid is **omitted** (left unestimated) rather than reported as a misleading zero,
so the underwriter sees "no estimate" instead of "no people".
"""

from __future__ import annotations

import csv
import math
from collections.abc import Sequence
from datetime import date
from functools import lru_cache
from importlib import resources

import httpx

from ..core.logging import get_logger
from .provider import RingEstimate

log = get_logger("population.census")

ACS_DATASET = "acs/acs5"
ACS_POP_VARIABLE = "B01003_001E"  # ACS total population
EARTH_RADIUS_MI = 3958.7613
_HTTP_TIMEOUT = 20.0


@lru_cache(maxsize=1)
def _county_centroids() -> list[tuple[str, float, float]]:
    """``(geoid, lat, lng)`` for every US county, from the bundled Gazetteer extract."""
    text = (
        resources.files("rjacq.population")
        .joinpath("data", "us_county_centroids.csv")
        .read_text(encoding="utf-8")
    )
    out: list[tuple[str, float, float]] = []
    for row in csv.DictReader(text.splitlines()):
        out.append((row["geoid"], float(row["lat"]), float(row["lng"])))
    return out


def _haversine_mi(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in miles between two lat/lng points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(a)))


class CensusACSProvider:
    """Population rings from US Census ACS 5-year county data (ADR-0009).

    Free public API; the key gates rate limits, not access to data — no PII is requested
    (aggregate population only). Construct via ``build_population_provider`` so the choice
    stays config-driven.
    """

    name = "census_acs"

    def __init__(self, api_key: str, *, year: int = 2022) -> None:
        self._api_key = api_key
        self._year = year
        # ACS 5-year vintage is labelled by its end year; stamp rings with that year-end.
        self._as_of = date(year, 12, 31)

    def _fetch_county_populations(self) -> dict[str, int]:
        """Nationwide county population keyed by 5-digit GEOID (one Census Data API call)."""
        url = f"https://api.census.gov/data/{self._year}/{ACS_DATASET}"
        params = {"get": ACS_POP_VARIABLE, "for": "county:*", "key": self._api_key}
        resp = httpx.get(url, params=params, timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        rows = resp.json()
        # rows[0] is the header [B01003_001E, state, county]; remaining rows are data.
        pops: dict[str, int] = {}
        for value, state, county in rows[1:]:
            try:
                pops[f"{state}{county}"] = int(value)
            except (TypeError, ValueError):
                continue  # null/suppressed value — skip rather than guess
        return pops

    def estimate_rings(self, lat: float, lng: float, radii: Sequence[int]) -> list[RingEstimate]:
        try:
            pops = self._fetch_county_populations()
        except (httpx.HTTPError, ValueError) as exc:
            # Graceful: a provider hiccup leaves rings unestimated, never fabricated or zeroed.
            log.warning("population.census_fetch_failed", error=str(exc), year=self._year)
            return []
        # Distance from the acquisition to every county centroid, computed once.
        distances = [
            (geoid, _haversine_mi(lat, lng, clat, clng))
            for geoid, clat, clng in _county_centroids()
        ]
        estimates: list[RingEstimate] = []
        for radius in radii:
            total = 0
            captured = 0
            for geoid, dist in distances:
                if dist <= radius and (pop := pops.get(geoid)) is not None:
                    total += pop
                    captured += 1
            # Omit a ring that captures no county centroid (coarse grain) — unestimated, not 0.
            if captured:
                estimates.append(
                    RingEstimate(radius_mi=radius, population=total, as_of=self._as_of)
                )
        if estimates:
            log.info(
                "population.census_estimated",
                year=self._year,
                rings=len(estimates),
                counties=len(pops),
            )
        return estimates

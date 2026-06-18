"""Census ACS provider tests (ADR-0009): radius aggregation, omission, fetch fallback, factory.

These exercise the pure aggregation logic with a controlled centroid set and a stubbed Census
fetch — no network. The acquisition sits at (35.6, -82.6); fixtures share that longitude so distance
reduces to ~69.05 mi per degree of latitude, making the expected ring membership obvious.
"""

from __future__ import annotations

import httpx
import pytest
from rjacq.core.config import settings
from rjacq.population import census, provider
from rjacq.population.census import CensusACSProvider

ACQUISITION_LAT, ACQUISITION_LNG = 35.6, -82.6

# (geoid, lat, lng): same longitude as the acquisition → distance ≈ |Δlat| * 69.05 mi.
FIXTURE_CENTROIDS = [
    ("11111", 35.60, -82.60),  # ~0 mi   → every ring
    ("22222", 35.90, -82.60),  # ~20.7mi → 25/50/100/150
    ("33333", 36.30, -82.60),  # ~48.3mi → 50/100/150 (outside 25)
    ("44444", 30.00, -82.60),  # ~386mi  → none
]
FIXTURE_POPS = {"11111": 1000, "22222": 2000, "33333": 3000, "44444": 4000}


@pytest.fixture
def stub_provider(monkeypatch: pytest.MonkeyPatch) -> CensusACSProvider:
    monkeypatch.setattr(census, "_county_centroids", lambda: list(FIXTURE_CENTROIDS))
    p = CensusACSProvider("test-key", year=2022)
    monkeypatch.setattr(p, "_fetch_county_populations", lambda: dict(FIXTURE_POPS))
    return p


def test_aggregates_population_by_radius(stub_provider: CensusACSProvider) -> None:
    out = stub_provider.estimate_rings(ACQUISITION_LAT, ACQUISITION_LNG, [25, 50, 100])
    rings = {e.radius_mi: e for e in out}
    assert rings[25].population == 3000  # 11111 + 22222
    assert rings[50].population == 6000  # + 33333
    assert rings[100].population == 6000  # 44444 (~386 mi) excluded
    assert rings[25].as_of.year == 2022  # ACS vintage stamped for provenance


def test_omits_ring_with_no_county_centroid(monkeypatch: pytest.MonkeyPatch) -> None:
    # Move the acquisition south so nothing falls within 25 mi: the inner ring is omitted.
    monkeypatch.setattr(census, "_county_centroids", lambda: list(FIXTURE_CENTROIDS))
    p = CensusACSProvider("test-key")
    monkeypatch.setattr(p, "_fetch_county_populations", lambda: dict(FIXTURE_POPS))
    rings = {e.radius_mi: e for e in p.estimate_rings(34.9, -82.6, [25, 50, 100])}
    assert 25 not in rings  # nearest centroid ~48 mi away → unestimated, never 0
    assert rings[50].population == 1000  # only 11111 (~48 mi) inside 50
    assert rings[100].population == 6000  # 11111 + 22222 + 33333


def test_fetch_failure_returns_no_rings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(census, "_county_centroids", lambda: list(FIXTURE_CENTROIDS))
    p = CensusACSProvider("test-key")

    def boom() -> dict[str, int]:
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(p, "_fetch_county_populations", boom)
    # Graceful degradation: rings stay unestimated rather than fabricated/zeroed.
    assert p.estimate_rings(ACQUISITION_LAT, ACQUISITION_LNG, [25, 50]) == []


def test_bundled_centroids_load() -> None:
    centroids = census._county_centroids()
    assert len(centroids) > 3000  # every US county
    geoid, lat, lng = centroids[0]
    assert len(geoid) == 5 and 18.0 < lat < 72.0 and -180.0 < lng < -60.0


def test_factory_selects_census_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "population_provider", "census")
    monkeypatch.setattr(settings, "population_provider_api_key", "k")
    monkeypatch.setattr(settings, "census_acs_year", 2022)
    built = provider.build_population_provider()
    assert isinstance(built, CensusACSProvider)


def test_factory_none_when_unconfigured_or_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "population_provider", None)
    monkeypatch.setattr(settings, "population_provider_api_key", None)
    assert provider.build_population_provider() is None
    # A key without a provider name, or an unrecognized provider, both fall back to None.
    monkeypatch.setattr(settings, "population_provider", "esri")
    monkeypatch.setattr(settings, "population_provider_api_key", "k")
    assert provider.build_population_provider() is None

"""Comp discovery: pure parsing/geometry + the geocode→discover service flow (hermetic, no network).

External HTTP is monkeypatched, so these never touch Overpass/Google/Nominatim.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from rjacq.comps import repository as comp_repo
from rjacq.comps import service
from rjacq.comps.distance import COMP_RADIUS_MILES, haversine_miles
from rjacq.comps.geocode import GeocodeResult, address_query
from rjacq.comps.sources import (
    RawComp,
    build_overpass_query,
    parse_google_places,
    parse_overpass,
    tile_centers,
)
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import AcquisitionStatus, Phase, PropertyType
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── pure: parsing + geometry ──────────────────────────────────────────────────


def test_address_query_skips_blanks() -> None:
    assert address_query("123 Main St", "Austin", "TX", "78701") == "123 Main St, Austin, TX, 78701"
    assert address_query(None, "Austin", "TX", None) == "Austin, TX"
    assert address_query(None, None, None, None) == ""


def test_build_overpass_query_radius_and_tags() -> None:
    q = build_overpass_query(30.0, -97.0, 50.0)
    assert "around:80467,30.000000,-97.000000" in q  # 50 mi → metres
    assert '"tourism"="caravan_site"' in q and '"leisure"="marina"' in q
    assert "out center tags" in q


def test_parse_overpass_nodes_ways_and_skips_unnamed() -> None:
    data = {
        "elements": [
            {"type": "node", "id": 1, "lat": 30.1, "lon": -97.1, "tags": {"name": "Pecan RV Park"}},
            {  # way → coords live under center
                "type": "way",
                "id": 2,
                "center": {"lat": 30.2, "lon": -97.2},
                "tags": {"name": "Lakeside Camp", "tourism": "camp_site"},
            },
            {"type": "node", "id": 3, "lat": 30.3, "lon": -97.3, "tags": {"leisure": "marina"}},
        ]
    }
    comps = parse_overpass(data)
    assert [c.name for c in comps] == ["Pecan RV Park", "Lakeside Camp"]  # unnamed marina dropped
    assert comps[1].lat == 30.2 and comps[1].external_ref == "way/2" and comps[1].source == "osm"


def test_parse_google_places() -> None:
    data = {
        "results": [
            {
                "name": "Hill Country RV Resort",
                "place_id": "abc123",
                "geometry": {"location": {"lat": 30.05, "lng": -97.05}},
                "rating": 4.4,
                "price_level": 2,
                "types": ["rv_park", "lodging"],
            },
            {"name": "No Geo", "place_id": "x"},  # missing geometry → skipped
        ]
    }
    comps = parse_google_places(data)
    assert len(comps) == 1
    assert comps[0].external_ref == "abc123" and comps[0].raw["rating"] == 4.4


def test_overpass_falls_back_to_a_second_mirror(monkeypatch: pytest.MonkeyPatch) -> None:
    """A throttled/timed-out mirror doesn't sink discovery: the source moves to the next endpoint
    and returns its result."""
    import httpx
    from rjacq.comps import sources as comp_sources
    from rjacq.core.config import settings

    good_url = settings.overpass_endpoints[1]
    calls: list[str] = []

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"elements": [{"type": "node", "id": 9, "lat": 30.1, "lon": -97.1,
                                  "tags": {"name": "Mirror RV Park"}}]}

    def fake_post(url: str, **kwargs: object) -> _Resp:
        calls.append(url)
        if url != good_url:
            raise httpx.ConnectError("boom")
        return _Resp()

    monkeypatch.setattr(comp_sources.time, "sleep", lambda _s: None)
    monkeypatch.setattr(httpx, "post", fake_post)
    comps = comp_sources.OpenStreetMapSource().discover(30.0, -97.0, 50.0)
    assert [c.name for c in comps] == ["Mirror RV Park"]
    assert good_url in calls and calls[0] == settings.overpass_endpoints[0]


def test_tile_centers_cover_the_disc() -> None:
    """Every point of the 50-mi disc is within a tile's radius of some tile center (no gaps)."""
    lat, lng, tile_r = 39.0, -105.0, 30.0
    centers = tile_centers(lat, lng, COMP_RADIUS_MILES, tile_radius_miles=tile_r)
    assert (lat, lng) in centers
    # sample points around the rim of the 50-mi disc; each must be covered by some tile
    import math

    for deg in range(0, 360, 30):
        ang = math.radians(deg)
        plat = lat + (49.0 * math.cos(ang)) / 69.0
        plng = lng + (49.0 * math.sin(ang)) / (69.0 * math.cos(math.radians(lat)))
        covered = any(haversine_miles(plat, plng, clat, clng) <= tile_r for clat, clng in centers)
        assert covered, f"rim point at {deg}° not covered"


# ── service flow against real Postgres (HTTP + sources stubbed) ────────────────


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


class _StubSource:
    name = "stub"

    def __init__(self, comps: list[RawComp]) -> None:
        self._comps = comps

    def discover(self, lat: float, lng: float, radius_miles: float) -> list[RawComp]:
        return self._comps


class _FailingSource:
    name = "boom"

    def discover(self, lat: float, lng: float, radius_miles: float) -> list[RawComp]:
        raise RuntimeError("overpass timed out")


class _StubGeocoder:
    def __init__(self, result: GeocodeResult | None) -> None:
        self._result = result

    def geocode(self, query: str) -> GeocodeResult | None:
        return self._result


async def _acquisition(session: AsyncSession, *, with_coords: bool) -> str:
    aid = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Acquisition(
            acquisition_id=aid,
            name="Comp Test Park",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
            address_line1="1 Resort Rd",
            city="Austin",
            state="TX",
            zip="78701",
            lat=30.2672 if with_coords else None,
            lng=-97.7431 if with_coords else None,
        )
    )
    await session.flush()
    return aid


async def test_ensure_location_geocodes_and_persists(session: AsyncSession) -> None:
    aid = await _acquisition(session, with_coords=False)
    geocoder = _StubGeocoder(GeocodeResult(30.2672, -97.7431, "stub"))
    lat, lng = await service.ensure_location(session, aid, geocoder=geocoder)
    assert (round(lat, 4), round(lng, 4)) == (30.2672, -97.7431)
    acquisition = await session.get(Acquisition, aid)
    assert acquisition is not None and acquisition.lat is not None  # persisted for reuse


async def test_ensure_location_errors_without_address(session: AsyncSession) -> None:
    aid = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Acquisition(
            acquisition_id=aid,
            name="No Address",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
        )
    )
    await session.flush()
    with pytest.raises(service.CompError) as exc:
        await service.ensure_location(session, aid, geocoder=_StubGeocoder(None))
    assert exc.value.code == "no_address"


async def test_discover_filters_radius_and_is_idempotent(session: AsyncSession) -> None:
    aid = await _acquisition(session, with_coords=True)
    near = RawComp("Near RV", 30.30, -97.74, None, "stub", "n1")  # ~2 mi
    far = RawComp("Far RV", 31.80, -97.74, None, "stub", "f1")  # ~105 mi → excluded
    inserted = await service.discover_comps(
        session,
        acquisition_id=aid,
        acquisition_lat=30.2672,
        acquisition_lng=-97.7431,
        sources=[_StubSource([near, far])],
        enricher=None,
    )
    assert inserted == 1
    comps = await comp_repo.list_comps(session, aid)
    assert [c.name for c in comps] == ["Near RV"]
    assert comps[0].distance_mi is not None and comps[0].distance_mi < Decimal("5")

    # Re-running replaces rather than duplicates (refresh-replace).
    again = await service.discover_comps(
        session,
        acquisition_id=aid,
        acquisition_lat=30.2672,
        acquisition_lng=-97.7431,
        sources=[_StubSource([near])],
        enricher=None,
    )
    assert again == 1
    assert len(await comp_repo.list_comps(session, aid)) == 1  # not 2


async def test_discover_keeps_manual_adds(session: AsyncSession) -> None:
    aid = await _acquisition(session, with_coords=True)
    await service.add_manual(
        session,
        acquisition_id=aid,
        url=None,
        name="Hand-added Resort",
        lat=30.27,
        lng=-97.75,
        avg_rate=Decimal("55"),
        acquisition_lat=30.2672,
        acquisition_lng=-97.7431,
        enricher=None,
    )
    await service.discover_comps(
        session,
        acquisition_id=aid,
        acquisition_lat=30.2672,
        acquisition_lng=-97.7431,
        sources=[_StubSource([RawComp("Auto RV", 30.28, -97.74, None, "stub", "a1")])],
        enricher=None,
    )
    names = {c.name for c in await comp_repo.list_comps(session, aid)}
    assert names == {"Hand-added Resort", "Auto RV"}  # manual survives the refresh


async def test_discover_raises_when_every_source_fails(session: AsyncSession) -> None:
    """All sources erroring is a transient outage, not "no comps nearby" — surface it as an error
    (so the UI can prompt a retry) rather than silently returning zero."""
    aid = await _acquisition(session, with_coords=True)
    with pytest.raises(service.CompError) as exc:
        await service.discover_comps(
            session,
            acquisition_id=aid,
            acquisition_lat=30.2672,
            acquisition_lng=-97.7431,
            sources=[_FailingSource()],
            enricher=None,
        )
    assert exc.value.code == "sources_unavailable"


async def test_discover_zero_results_is_not_an_error(session: AsyncSession) -> None:
    """A source that answers with nothing nearby (even alongside a failing one) is a legitimate
    empty result, not an outage — returns 0 without raising."""
    aid = await _acquisition(session, with_coords=True)
    inserted = await service.discover_comps(
        session,
        acquisition_id=aid,
        acquisition_lat=30.2672,
        acquisition_lng=-97.7431,
        sources=[_FailingSource(), _StubSource([])],
        enricher=None,
    )
    assert inserted == 0


async def test_set_rate_updates_comp(session: AsyncSession) -> None:
    aid = await _acquisition(session, with_coords=True)
    comp = await service.add_manual(
        session,
        acquisition_id=aid,
        url=None,
        name="Hand-added",
        lat=30.27,
        lng=-97.75,
        avg_rate=None,
        acquisition_lat=30.2672,
        acquisition_lng=-97.7431,
        enricher=None,
    )
    updated = await service.set_rate(session, aid, comp.comp_id, Decimal("62.50"))
    assert updated.avg_rate == Decimal("62.50")
    with pytest.raises(service.CompError) as exc:
        await service.set_rate(session, aid, "cp_missing", Decimal("10"))
    assert exc.value.code == "not_found"


async def test_enrich_comp_gated_without_keys(session: AsyncSession) -> None:
    aid = await _acquisition(session, with_coords=True)
    comp = await service.add_manual(
        session,
        acquisition_id=aid,
        url=None,
        name="No Keys",
        lat=30.27,
        lng=-97.75,
        avg_rate=None,
        acquisition_lat=30.2672,
        acquisition_lng=-97.7431,
        enricher=None,
    )
    # No Google/Anthropic enricher → a clear error, never a fabricated score.
    with pytest.raises(service.CompError) as exc:
        await service.enrich_comp(
            session, aid, comp.comp_id, review_enricher=None, google_api_key=None
        )
    assert exc.value.code == "not_configured"

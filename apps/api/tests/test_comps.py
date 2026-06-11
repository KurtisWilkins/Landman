"""Comp intelligence tests (§5.6): radius filtering, source contract, manual-add enrichment."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from rjacq.comps import service
from rjacq.comps.distance import haversine_miles, within_radius
from rjacq.comps.enrichment import Enrichment
from rjacq.comps.service import CompError
from rjacq.comps.sources import RawComp, build_sources
from rjacq.models.deals import Deal
from rjacq.models.enums import DealStatus, Phase, PropertyType
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Asheville, NC (a deal location) and a point ~8 mi away vs ~120 mi away.
DEAL_LAT, DEAL_LNG = 35.5951, -82.6040
NEAR_LAT, NEAR_LNG = 35.61, -82.55  # ~3 mi
FAR_LAT, FAR_LNG = 34.85, -82.40  # Greenville SC, ~50+ mi south


class FakeSource:
    name = "fake"

    def __init__(self, comps: list[RawComp]) -> None:
        self._comps = comps

    def discover(self, lat: float, lng: float, radius_miles: float) -> list[RawComp]:
        return self._comps


class FailingSource:
    name = "broken"

    def discover(self, lat: float, lng: float, radius_miles: float) -> list[RawComp]:
        raise RuntimeError("boom")


class FakeEnricher:
    def enrich(self, comp: RawComp) -> Enrichment:
        return Enrichment(
            ai_summary="Premium tier",
            amenity_score=90,
            sentiment_score=Decimal("4.6"),
            best_snippet="Loved it",
            worst_snippet="Pricey",
        )


# ── distance / radius ───────────────────────────────────────────────────────


def test_haversine_and_radius() -> None:
    assert haversine_miles(DEAL_LAT, DEAL_LNG, NEAR_LAT, NEAR_LNG) < 10
    assert haversine_miles(DEAL_LAT, DEAL_LNG, FAR_LAT, FAR_LNG) > 50
    assert within_radius(DEAL_LAT, DEAL_LNG, NEAR_LAT, NEAR_LNG)
    assert not within_radius(DEAL_LAT, DEAL_LNG, FAR_LAT, FAR_LNG)


# ── source gating (D-22) ────────────────────────────────────────────────────


def test_build_sources_empty_when_unconfigured() -> None:
    assert build_sources() == []  # no API keys, scrapers off


def test_build_sources_includes_api_when_keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    from rjacq.comps import sources as src

    monkeypatch.setattr(src.settings, "google_places_api_key", "k")
    monkeypatch.setattr(src.settings, "scrapers_enabled", False)
    names = [s.name for s in build_sources()]
    assert "google" in names
    assert names == ["google"]  # scrapers stay off behind the flag


# ── discovery + radius filtering (real Postgres) ────────────────────────────


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _deal(session: AsyncSession) -> str:
    deal_id = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Deal(
            deal_id=deal_id,
            name="Comp Test Park",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=DealStatus.ACTIVE,
            lat=DEAL_LAT,
            lng=DEAL_LNG,
        )
    )
    await session.flush()
    return deal_id


async def test_discover_filters_by_radius_and_survives_failures(session: AsyncSession) -> None:
    deal_id = await _deal(session)
    near = RawComp("Near Park", NEAR_LAT, NEAR_LNG, Decimal("91"), "fake")
    far = RawComp("Far Park", FAR_LAT, FAR_LNG, Decimal("80"), "fake")
    count = await service.discover_comps(
        session,
        deal_id=deal_id,
        deal_lat=DEAL_LAT,
        deal_lng=DEAL_LNG,
        sources=[FakeSource([near, far]), FailingSource()],  # failing source must not block
        enricher=FakeEnricher(),
    )
    await session.commit()
    assert count == 1  # only the in-radius comp persisted
    comp_set = await service.build_comp_set(session, deal_id)
    assert len(comp_set.comps) == 1
    c = comp_set.comps[0]
    assert c.name == "Near Park"
    assert c.amenity_score == 90  # enriched
    assert c.amenity_rank == 1
    assert c.distance_mi is not None and c.distance_mi < Decimal("10")


async def test_manual_add_by_fields_enriched(session: AsyncSession) -> None:
    deal_id = await _deal(session)
    comp = await service.add_manual(
        session,
        deal_id=deal_id,
        url=None,
        name="Blue Ridge Basecamp",
        lat=NEAR_LAT,
        lng=NEAR_LNG,
        avg_rate=Decimal("91"),
        deal_lat=DEAL_LAT,
        deal_lng=DEAL_LNG,
        enricher=FakeEnricher(),
    )
    await session.commit()
    assert comp.is_manual is True
    assert comp.sentiment_score == Decimal("4.6")
    assert comp.distance_mi is not None and comp.distance_mi < Decimal("10")


async def test_manual_add_requires_url_or_name(session: AsyncSession) -> None:
    deal_id = await _deal(session)
    with pytest.raises(CompError) as ei:
        await service.add_manual(
            session,
            deal_id=deal_id,
            url=None,
            name=None,
            lat=None,
            lng=None,
            avg_rate=None,
            deal_lat=None,
            deal_lng=None,
            enricher=None,
        )
    assert ei.value.code == "invalid_manual_add"


async def test_comp_set_visualization_points(session: AsyncSession) -> None:
    deal_id = await _deal(session)
    await service.add_manual(
        session,
        deal_id=deal_id,
        url="https://x",
        name="X",
        lat=NEAR_LAT,
        lng=NEAR_LNG,
        avg_rate=Decimal("75"),
        deal_lat=DEAL_LAT,
        deal_lng=DEAL_LNG,
        enricher=FakeEnricher(),
    )
    await session.commit()
    cs = await service.build_comp_set(session, deal_id)
    assert cs.visualization is not None
    assert cs.visualization.points[0].avg_rate == Decimal("75")
    assert cs.visualization.points[0].sentiment_score == Decimal("4.6")

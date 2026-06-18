"""Population-rings tests (§5.5): provider gating, auto-pull, override provenance, endpoint."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import date

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import AcquisitionStatus, Phase, PropertyType
from rjacq.models.market import RING_RADII_MILES
from rjacq.population import service
from rjacq.population.provider import RingEstimate, build_population_provider
from rjacq.population.service import PopulationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ADMIN = {"Authorization": "Bearer dev admin"}


class FakeProvider:
    name = "fake_census"

    def estimate_rings(self, lat: float, lng: float, radii: Sequence[int]) -> list[RingEstimate]:
        # Toy monotonic estimate: bigger radius → more people.
        return [RingEstimate(r, r * 1000, date(2024, 1, 1)) for r in radii]


def test_provider_none_when_unconfigured() -> None:
    assert build_population_provider() is None


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _acquisition(
    session: AsyncSession, *, lat: float | None = 35.6, lng: float | None = -82.6
) -> str:
    acquisition_id = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Acquisition(
            acquisition_id=acquisition_id,
            name="Pop Test Park",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
            lat=lat,
            lng=lng,
        )
    )
    await session.flush()
    return acquisition_id


async def test_refresh_pulls_all_rings(session: AsyncSession) -> None:
    acquisition_id = await _acquisition(session)
    n = await service.refresh_rings(
        session, acquisition_id, lat=35.6, lng=-82.6, provider=FakeProvider()
    )
    await session.commit()
    assert n == len(RING_RADII_MILES)
    doc = await service.get_rings(session, acquisition_id)
    by_radius = {r.radius_mi: r for r in doc.rings}
    assert set(by_radius) == set(RING_RADII_MILES)
    assert by_radius[50].population == 50000  # effective = baseline
    assert by_radius[50].source == "fake_census"
    assert by_radius[50].is_override is False


async def test_refresh_noop_without_provider_or_geocode(session: AsyncSession) -> None:
    acquisition_id = await _acquisition(session, lat=None, lng=None)
    assert (
        await service.refresh_rings(
            session, acquisition_id, lat=None, lng=None, provider=FakeProvider()
        )
        == 0
    )
    assert (
        await service.refresh_rings(session, acquisition_id, lat=35.6, lng=-82.6, provider=None)
        == 0
    )


async def test_override_keeps_baseline_and_refresh_preserves_override(
    session: AsyncSession,
) -> None:
    acquisition_id = await _acquisition(session)
    await service.refresh_rings(
        session, acquisition_id, lat=35.6, lng=-82.6, provider=FakeProvider()
    )
    await service.override_ring(
        session,
        acquisition_id,
        radius_mi=25,
        population=42000,
        note="Local knowledge",
        author="kurtis",
    )
    await session.commit()

    doc = await service.get_rings(session, acquisition_id)
    ring25 = next(r for r in doc.rings if r.radius_mi == 25)
    assert ring25.population == 42000  # effective = override
    assert ring25.baseline_population == 25000  # baseline retained (provenance)
    assert ring25.is_override is True
    assert ring25.overridden_by == "kurtis"

    # A later refresh updates the baseline but never clobbers the override.
    await service.refresh_rings(
        session, acquisition_id, lat=35.6, lng=-82.6, provider=FakeProvider()
    )
    await session.commit()
    doc2 = await service.get_rings(session, acquisition_id)
    ring25b = next(r for r in doc2.rings if r.radius_mi == 25)
    assert ring25b.population == 42000  # override still wins
    assert ring25b.is_override is True


async def test_override_invalid_radius_raises(session: AsyncSession) -> None:
    acquisition_id = await _acquisition(session)
    with pytest.raises(PopulationError) as ei:
        await service.override_ring(
            session, acquisition_id, radius_mi=33, population=1, note=None, author="kurtis"
        )
    assert ei.value.code == "invalid_radius"


def test_create_acquisition_returns_market_block(migrated_db: str, client: TestClient) -> None:
    # Provider unconfigured → rings empty, but the endpoint persists the acquisition and returns the
    # market block (auto-pull activates once a provider is set).
    r = client.post(
        "/acquisitions",
        json={
            "name": "New Park",
            "property_type": "rv_resort",
            "address": {"lat": 35.6, "lng": -82.6},
        },
        headers=ADMIN,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["acquisition_id"].startswith("dl_")
    assert body["market"] == {"rings": []}

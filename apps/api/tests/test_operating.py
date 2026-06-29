"""Operational-input drivers (defaults engine, Part 1).

Pure driver math (billable units / needs-input) runs without a DB; the seed/edit service tests
run against real Postgres, mirroring test_labor_service.py.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import AcquisitionStatus, Phase, PropertyType, UnitType
from rjacq.models.property import Unit
from rjacq.schemas.operating import UnitGroupCreate, UnitGroupPatch
from rjacq.underwriting import operating_service
from rjacq.underwriting.operating import (
    UnitGroupInput,
    billable_unit_total,
    default_billable,
    units_need_input,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Pure driver math (no DB) ────────────────────────────────────────────────


def _g(category: str, count: int | None, billable: bool) -> UnitGroupInput:
    return UnitGroupInput(category=category, count=count, billable=billable)


def test_billable_total_sums_billable_excludes_tents() -> None:
    groups = [
        _g("rv_pad", 120, True),
        _g("cabin", 12, True),
        _g("glamping", 6, True),
        _g("tent", 8, False),  # excluded
    ]
    assert billable_unit_total(groups) == 138
    assert units_need_input(groups) is False


def test_needs_input_when_a_billable_group_has_no_count() -> None:
    groups = [_g("rv_pad", 120, True), _g("glamping", None, True)]
    assert units_need_input(groups) is True
    # The total still reflects what's known (the glamping gap is flagged, not guessed).
    assert billable_unit_total(groups) == 120


def test_needs_input_when_no_billable_group() -> None:
    assert units_need_input([_g("tent", 8, False)]) is True
    assert billable_unit_total([_g("tent", 8, False)]) == 0


def test_default_billable_categories() -> None:
    assert default_billable("rv_pad") and default_billable("cabin") and default_billable("glamping")
    assert not default_billable("tent")
    assert not default_billable("marina_slip")


# ── Seed / edit service (real Postgres) ─────────────────────────────────────


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _acquisition(session: AsyncSession, *, site_count: int | None = None) -> str:
    aid = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Acquisition(
            acquisition_id=aid,
            name="Operating Test",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
            site_count=site_count,
        )
    )
    await session.flush()
    return aid


async def test_seed_from_unit_mix_aggregates_categories(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    session.add_all(
        [
            Unit(
                unit_id=f"u_{uuid.uuid4().hex[:8]}",
                acquisition_id=aid,
                unit_type=UnitType.RV_PULL_THROUGH,
                count=80,
            ),
            Unit(
                unit_id=f"u_{uuid.uuid4().hex[:8]}",
                acquisition_id=aid,
                unit_type=UnitType.RV_BACK_IN,
                count=40,
            ),
            Unit(
                unit_id=f"u_{uuid.uuid4().hex[:8]}",
                acquisition_id=aid,
                unit_type=UnitType.CABIN,
                count=10,
            ),
            Unit(
                unit_id=f"u_{uuid.uuid4().hex[:8]}",
                acquisition_id=aid,
                unit_type=UnitType.TENT,
                count=5,
            ),
        ]
    )
    await session.flush()
    doc = await operating_service.seed_operating(session, aid, actor="kurtis")
    cats = {r.category: r for r in doc.unit_groups}
    assert cats["rv_pad"].count == 120  # pull-through + back-in
    assert cats["rv_pad"].billable and cats["cabin"].billable
    assert cats["tent"].billable is False
    # 120 RV pads + 10 cabins; tents excluded.
    assert doc.billable_unit_total == 130
    assert doc.units_need_input is False


async def test_seed_without_units_prompts_and_uses_site_count(session: AsyncSession) -> None:
    aid = await _acquisition(session, site_count=95)
    doc = await operating_service.seed_operating(session, aid, actor="kurtis")
    cats = {r.category: r for r in doc.unit_groups}
    assert cats["rv_pad"].count == 95 and cats["rv_pad"].source == "om"
    assert cats["cabin"].count is None and cats["glamping"].count is None
    # Glamping/cabin still need counts → the dependent default can't be trusted yet.
    assert doc.units_need_input is True
    # Headcount has no OM source → always needs input after a bare seed.
    assert doc.headcount_needs_input is True


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    aid = await _acquisition(session, site_count=50)
    first = await operating_service.seed_operating(session, aid, actor="kurtis")
    again = await operating_service.seed_operating(session, aid, actor="kurtis")
    assert len(first.unit_groups) == len(again.unit_groups)


async def test_headcount_reads_from_labor_roster(session: AsyncSession) -> None:
    from rjacq.underwriting import labor_service

    aid = await _acquisition(session)
    # No roster yet → Operating headcount needs input (not stored here anymore).
    doc = await operating_service.get_operating(session, aid)
    assert doc.employee_headcount is None
    assert doc.headcount_needs_input is True
    # Seed the default roster (5 positions) → Operating reads the roster total, tagged "labor".
    await labor_service.seed_default_staffing(session, aid, actor="kurtis")
    doc = await operating_service.get_operating(session, aid)
    assert doc.employee_headcount == 5
    assert doc.headcount_source == "labor"
    assert doc.headcount_needs_input is False


async def test_edit_unit_count_recomputes_driver(session: AsyncSession) -> None:
    aid = await _acquisition(session, site_count=100)
    doc = await operating_service.seed_operating(session, aid, actor="kurtis")
    glamping = next(r for r in doc.unit_groups if r.category == "glamping")
    doc = await operating_service.patch_unit_group(
        session, aid, UnitGroupPatch(unit_group_id=glamping.unit_group_id, count=8), actor="kurtis"
    )
    # 100 RV pads + 8 glamping now captured (cabins still None → still needs input).
    assert doc.billable_unit_total == 108
    edited = next(r for r in doc.unit_groups if r.category == "glamping")
    assert edited.source == "manual"


async def test_add_custom_subtype_defaults_billable(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    doc = await operating_service.add_unit_group(
        session,
        aid,
        UnitGroupCreate(category="rv_pad_premium", label="RV pads — premium", count=15),
        actor="kurtis",
    )
    grp = next(r for r in doc.unit_groups if r.category == "rv_pad_premium")
    assert grp.billable is True  # a custom unit grouping bills by default
    assert grp.count == 15 and doc.billable_unit_total == 15


async def test_remove_unit_group(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    doc = await operating_service.add_unit_group(
        session, aid, UnitGroupCreate(category="cabin", count=12), actor="kurtis"
    )
    grp = doc.unit_groups[0]
    doc = await operating_service.remove_unit_group(session, aid, grp.unit_group_id, actor="kurtis")
    assert doc.unit_groups == []


async def test_electric_seeds_from_prior_actual(session: AsyncSession, monkeypatch) -> None:
    aid = await _acquisition(session)

    async def fake_prior(_s, _aid):  # noqa: ANN001
        return Decimal("48000")

    monkeypatch.setattr(operating_service, "_electric_prior_actual", fake_prior)
    doc = await operating_service.seed_operating(session, aid, actor="kurtis")
    assert doc.electric_annual == Decimal("48000")
    assert doc.electric_source == "actuals"
    assert doc.electric_needs_input is False

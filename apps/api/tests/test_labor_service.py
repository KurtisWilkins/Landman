"""Labor service → budget feed (real Postgres). Pure cost math is covered in test_labor.py."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import AccountLevel, AcquisitionStatus, Phase, PropertyType
from rjacq.models.reference import GLAccount
from rjacq.schemas.labor import LaborPositionCreate
from rjacq.underwriting import budget_service, labor_service
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _acquisition(session: AsyncSession) -> str:
    aid = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Acquisition(
            acquisition_id=aid,
            name="Labor Test",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
        )
    )
    await session.flush()
    return aid


async def _account(session: AsyncSession, code: str, section: str) -> None:
    session.add(
        GLAccount(
            account_code=code,
            level=AccountLevel.LEAF,
            name=f"Acct {code}",
            section=section,
            default_noi_placement="above",
            active=True,
        )
    )
    await session.flush()


async def test_labor_feeds_budget_wages(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    await _account(session, "600140", "Expense")  # wages target
    await labor_service.add_position(
        session,
        aid,
        LaborPositionCreate(
            role="general_manager",
            employment_type="full_time",
            season="year_round",
            hourly_rate=Decimal("28"),
        ),
        actor="kurtis",
    )
    doc = await labor_service.get_labor(session, aid)
    assert doc.totals.wages == Decimal("58240")  # 40 × 28 × 52

    budget = await budget_service.get_budget(session, aid)
    row = next(r for r in budget.rows if r.account_code == "600140")
    assert row.year1_annual == Decimal("58240") and row.source == "labor"


async def test_work_camper_revenue_and_credit(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    await _account(session, "400110", "Income")  # RV Extended Stay
    await _account(session, "421300", "Income")  # Work Camper Campsite Credit (contra)
    await labor_service.add_position(
        session,
        aid,
        LaborPositionCreate(
            role="maintenance",
            employment_type="part_time",
            season="year_round",
            is_work_camper=True,
            site_weekly_rate=Decimal("300"),
            campsite_credit_weekly=Decimal("300"),
        ),
        actor="kurtis",
    )
    doc = await labor_service.get_labor(session, aid)
    assert doc.totals.wages == Decimal("0")  # work camper draws no cash wage
    assert doc.totals.extended_stay_revenue == Decimal("15600")  # 300 × 52
    assert doc.totals.work_camper_credit == Decimal("15600")

    budget = await budget_service.get_budget(session, aid)
    ext = next(r for r in budget.rows if r.account_code == "400110")
    credit = next(r for r in budget.rows if r.account_code == "421300")
    assert ext.year1_annual == Decimal("15600")
    assert credit.year1_annual == Decimal("-15600")  # contra-revenue reduces revenue


async def test_seed_roster_from_om_tags_om(session: AsyncSession) -> None:
    from rjacq.underwriting import budget_service

    aid = await _acquisition(session)
    doc = await labor_service.seed_roster(
        session,
        aid,
        [("General Manager", 1, Decimal("30")), ("Maintenance Crew", 2, Decimal("18"))],
        actor="kurtis",
    )
    by_role = {r.role: r for r in doc.positions}
    assert by_role["general_manager"].source == "om"
    assert by_role["maintenance"].headcount == 2
    assert doc.totals.headcount == 3  # roster SSOT = 1 + 2
    # The Operating tab / payroll default both read this same number.
    assert await budget_service.roster_headcount(session, aid) == 3


async def test_seed_roster_empty_falls_back_to_default(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    doc = await labor_service.seed_roster(session, aid, [], actor="kurtis")
    assert len(doc.positions) == 5  # the default scenario (3 FT + 2 PT)
    assert all(p.source == "default" for p in doc.positions)
    assert doc.totals.headcount == 5


async def test_seed_roster_idempotent(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    await labor_service.seed_default_staffing(session, aid, actor="k")
    again = await labor_service.seed_roster(session, aid, [("Manager", 9, None)], actor="k")
    assert again.totals.headcount == 5  # no-op once positions exist

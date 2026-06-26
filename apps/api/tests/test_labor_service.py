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

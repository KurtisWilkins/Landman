"""Year-one budget tests (§5.5): pure prior-year/variance math + seed/get/patch service."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import AccountLevel, AcquisitionStatus, NoiPlacement, Phase, PropertyType
from rjacq.models.financials import FinancialLine, FinancialPeriod
from rjacq.models.reference import GLAccount
from rjacq.schemas.budget import BudgetCellUpdate
from rjacq.underwriting import budget_service
from rjacq.underwriting.budget import bucket_line_months, month_index_of, variance
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── pure math ────────────────────────────────────────────────────────────────


def test_month_index_of() -> None:
    assert month_index_of("JUN 25") == 6
    assert month_index_of("January 2026") == 1
    assert month_index_of("Sep-25") == 9
    assert month_index_of("_seller_line") is None  # provenance key
    assert month_index_of("may") is None  # no year → not a month column


def test_bucket_line_months() -> None:
    raw = {"JAN 25": "100", "FEB 25": "200.50", "_seller_line": "Site Rent", "_section": "Income"}
    assert bucket_line_months(raw) == {1: Decimal("100"), 2: Decimal("200.50")}


def test_variance() -> None:
    assert variance(Decimal("100"), Decimal("150")) == (Decimal("50"), Decimal("0.5"))
    abs_var, pct_var = variance(Decimal("0"), Decimal("100"))
    assert abs_var == Decimal("100") and pct_var is None  # new line → no %


# ── service (real Postgres) ───────────────────────────────────────────────────


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _acquisition(session: AsyncSession) -> tuple[str, str]:
    acquisition_id = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Acquisition(
            acquisition_id=acquisition_id,
            name="Budget Test Park",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
        )
    )
    period_id = f"fp_{uuid.uuid4().hex[:12]}"
    session.add(
        FinancialPeriod(
            period_id=period_id, acquisition_id=acquisition_id, label="T12", granularity="t12"
        )
    )
    await session.flush()
    return acquisition_id, period_id


async def _mapped_line(
    session: AsyncSession, acquisition_id: str, period_id: str, code: str, raw: dict[str, Any]
) -> None:
    session.add(
        FinancialLine(
            line_id=f"fl_{uuid.uuid4().hex[:12]}",
            acquisition_id=acquisition_id,
            period_id=period_id,
            account_code=code,
            account_level=AccountLevel.LEAF,
            amount=Decimal(sum(Decimal(str(v)) for k, v in raw.items() if not k.startswith("_"))),
            seller_source_line=raw.get("_seller_line", "line"),
            noi_placement=NoiPlacement.ABOVE,
            raw_payload=raw,
        )
    )
    await session.flush()


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


async def test_seed_prefills_year_one_from_actuals(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(session, code, "Income")
    await _mapped_line(
        session,
        acquisition_id,
        period_id,
        code,
        {"JAN 25": "100", "FEB 25": "150", "_seller_line": "Site Rent"},
    )

    await budget_service.seed_budget(session, acquisition_id)
    doc = await budget_service.get_budget(session, acquisition_id)
    row = next(r for r in doc.rows if r.account_code == code)
    assert row.source == "actuals"
    assert row.prior_months[0] == Decimal("100")  # Jan prior
    assert row.year1_months[0] == Decimal("100")  # prefilled from actuals
    assert row.prior_annual == Decimal("250")
    assert row.year1_annual == Decimal("250")
    assert row.var_abs == Decimal("0")
    assert doc.totals.year1_revenue == Decimal("250")


async def test_patch_cell_flips_override(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(session, code, "Income")
    await _mapped_line(
        session, acquisition_id, period_id, code, {"JAN 25": "100", "_seller_line": "Rent"}
    )
    await budget_service.seed_budget(session, acquisition_id)

    await budget_service.patch_cell(
        session,
        acquisition_id,
        BudgetCellUpdate(account_code=code, month_index=1, year1_amount=Decimal("500")),
        actor="kurtis",
    )
    doc = await budget_service.get_budget(session, acquisition_id)
    row = next(r for r in doc.rows if r.account_code == code)
    assert row.year1_months[0] == Decimal("500")  # edited
    assert row.year1_annual == Decimal("500")
    assert row.is_overridden is True
    # Prior year (read-only) is unchanged.
    assert row.prior_months[0] == Decimal("100")


# ── lock + flow-through ───────────────────────────────────────────────────────


async def test_lock_rolls_budget_into_stabilized(session: AsyncSession) -> None:
    from rjacq.underwriting import service as uw

    acquisition_id, period_id = await _acquisition(session)
    rev = f"r{uuid.uuid4().hex[:8]}"
    op = f"o{uuid.uuid4().hex[:8]}"
    await _account(session, rev, "Income")
    await _account(session, op, "Expense")
    await _mapped_line(
        session,
        acquisition_id,
        period_id,
        rev,
        {"JAN 25": "100", "FEB 25": "100", "_seller_line": "Rent"},
    )
    await _mapped_line(
        session,
        acquisition_id,
        period_id,
        op,
        {"JAN 25": "30", "FEB 25": "30", "_seller_line": "Utils"},
    )
    await budget_service.seed_budget(session, acquisition_id)

    assert await budget_service.locked_stabilized(session, acquisition_id) is None  # draft
    await budget_service.lock(session, acquisition_id, by="kurtis")
    assert await budget_service.locked_stabilized(session, acquisition_id) == (
        Decimal("200"),
        Decimal("60"),
    )
    # effective_stabilized now prefers the locked budget over the NOI bridge.
    revenue, opex = await uw.effective_stabilized(session, acquisition_id, None)
    assert revenue == Decimal("200") and opex == Decimal("60")


async def test_lock_blocked_by_unmapped(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(session, code, "Income")
    await _mapped_line(
        session, acquisition_id, period_id, code, {"JAN 25": "100", "_seller_line": "Rent"}
    )
    session.add(
        FinancialLine(
            line_id=f"fl_{uuid.uuid4().hex[:12]}",
            acquisition_id=acquisition_id,
            period_id=period_id,
            seller_source_line="Mystery",
            amount=Decimal("5"),  # account_code None → unmapped
        )
    )
    await session.flush()
    await budget_service.seed_budget(session, acquisition_id)
    with pytest.raises(budget_service.BudgetError):
        await budget_service.lock(session, acquisition_id, by="kurtis")


async def test_edit_invalidates_lock(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(session, code, "Income")
    await _mapped_line(
        session, acquisition_id, period_id, code, {"JAN 25": "100", "_seller_line": "Rent"}
    )
    await budget_service.seed_budget(session, acquisition_id)
    await budget_service.lock(session, acquisition_id, by="kurtis")
    assert (await budget_service.get_budget(session, acquisition_id)).status == "locked"

    await budget_service.patch_cell(
        session,
        acquisition_id,
        BudgetCellUpdate(account_code=code, month_index=1, year1_amount=Decimal("999")),
        actor="kurtis",
    )
    assert (await budget_service.get_budget(session, acquisition_id)).status == "draft"

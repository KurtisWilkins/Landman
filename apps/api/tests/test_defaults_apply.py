"""Defaults engine → budget application (real Postgres). The pure rule math is in
test_defaults_rules.py; this pins the budget wiring: contra sign, manual-sticks, revert,
subtree-aware gap-fill, and the driver-change recompute via the operating panel."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import AccountLevel, AcquisitionStatus, Phase, PropertyType
from rjacq.models.operating import OperationalInputs
from rjacq.models.reference import GLAccount
from rjacq.schemas.budget import BudgetLineCreate, BudgetLinePatch
from rjacq.schemas.operating import OperatingPatch
from rjacq.underwriting import budget_service, operating_service
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
            name="Defaults Test",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
        )
    )
    await session.flush()
    return aid


async def _account(
    session: AsyncSession, code: str, section: str, *, parent: str | None = None
) -> None:
    session.add(
        GLAccount(
            account_code=code,
            parent_code=parent,
            level=AccountLevel.LEAF,
            name=f"Acct {code}",
            section=section,
            default_noi_placement="above",
            active=True,
        )
    )
    await session.flush()


def _row(doc, code: str):  # noqa: ANN001
    return next((r for r in doc.rows if r.account_code == code), None)


async def test_seed_posts_fixed_defaults(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    await _account(session, "600410", "Expense")  # shield
    await _account(session, "601010", "Expense")  # seo / subscription marketing
    doc = await budget_service.seed_budget(session, aid)
    assert _row(doc, "600410").year1_annual == Decimal("12000")  # 1,000/mo
    assert _row(doc, "600410").source == "default"
    assert _row(doc, "601010").year1_annual == Decimal("10200")  # 850/mo


async def test_billback_posts_negative_contra(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    await _account(session, "605415", "Expense")  # Utility Recovery (contra)
    session.add(
        OperationalInputs(
            acquisition_id=aid, electric_annual=Decimal("48000"), electric_source="manual"
        )
    )
    await session.flush()
    doc = await budget_service.seed_budget(session, aid)
    # 62% × 48,000 = 29,760, posted NEGATIVE so it nets down opex.
    assert _row(doc, "605415").year1_annual == Decimal("-29760.00")


async def test_manual_edit_sticks_then_reverts(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    await _account(session, "600410", "Expense")
    await budget_service.seed_budget(session, aid)
    line_id = _row(await budget_service.get_budget(session, aid), "600410").line_id
    # Manually edit the default; re-applying defaults must NOT clobber it.
    await budget_service.patch_line(
        session, aid, BudgetLinePatch(line_id=line_id, year1_amount=Decimal("5000")), actor="k"
    )
    doc = await budget_service.apply_defaults(session, aid, actor="k")
    assert _row(doc, "600410").year1_annual == Decimal("5000")
    assert _row(doc, "600410").is_overridden is True
    assert _row(doc, "600410").revertible is True  # the UI can offer revert-to-default
    # Revert re-links it to the rule.
    doc = await budget_service.revert_to_default(session, aid, line_id, actor="k")
    assert _row(doc, "600410").year1_annual == Decimal("12000")
    assert _row(doc, "600410").source == "default"


async def test_gapfill_skips_when_subtree_has_actuals(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    await _account(session, "400000", "Income")  # gross-revenue base
    await _account(session, "605400", "Expense")  # Utilities (parent)
    await _account(session, "605410", "Expense", parent="605400")  # Electric (child)
    await budget_service.seed_budget(session, aid)
    await budget_service.add_line(
        session,
        aid,
        BudgetLineCreate(account_code="400000", year1_amount=Decimal("1000000")),
        actor="k",
    )
    # Seller already mapped utility detail → the coarse 17.5% default must NOT post on 605400.
    await budget_service.add_line(
        session,
        aid,
        BudgetLineCreate(account_code="605410", year1_amount=Decimal("20000")),
        actor="k",
    )
    doc = await budget_service.apply_defaults(session, aid, actor="k")
    assert _row(doc, "605400") is None  # utilities skipped — no double-count


async def test_utilities_posts_when_bucket_empty(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    await _account(session, "400000", "Income")
    await _account(session, "605400", "Expense")
    await budget_service.seed_budget(session, aid)
    await budget_service.add_line(
        session,
        aid,
        BudgetLineCreate(account_code="400000", year1_amount=Decimal("1000000")),
        actor="k",
    )
    doc = await budget_service.apply_defaults(session, aid, actor="k")
    assert _row(doc, "605400").year1_annual == Decimal("175000.000")  # 17.5% of 1,000,000


async def test_driver_change_recomputes_payroll_via_operating(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    await _account(session, "600145", "Expense")  # Payroll Budget Allocation
    await budget_service.seed_budget(session, aid)
    # No headcount yet → the payroll-budget default can't compute (needs input).
    assert _row(await budget_service.get_budget(session, aid), "600145") is None
    # Set headcount via the operating panel → the dependent default recomputes automatically.
    await operating_service.patch_operating(
        session, aid, OperatingPatch(employee_headcount=6), actor="k"
    )
    doc = await budget_service.get_budget(session, aid)
    assert _row(doc, "600145").year1_annual == Decimal("6120")  # 85 × 6 × 12
    assert _row(doc, "600145").source == "default"

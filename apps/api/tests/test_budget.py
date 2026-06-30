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
from rjacq.schemas.budget import BudgetLineCreate, BudgetLinePatch, BudgetLineRef
from rjacq.underwriting import budget_service
from rjacq.underwriting.budget import (
    GridLine,
    bucket_line_months,
    month_index_of,
    roll_up,
    variance,
)
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


def test_roll_up_two_columns() -> None:
    lines = [
        GridLine("above", False, Decimal("420000"), Decimal("441000")),  # revenue
        GridLine("above", False, Decimal("38500"), Decimal("40000")),  # revenue
        GridLine("above", True, Decimal("96000"), Decimal("99000")),  # expense
        GridLine("above", True, Decimal("41300"), Decimal("43000")),  # expense
        GridLine("below", True, Decimal("80000"), Decimal("80000")),  # debt service — excluded
        GridLine("non_operating", True, Decimal("5000"), Decimal("0")),  # excluded
    ]
    t = roll_up(lines)
    assert t.prior_revenue == Decimal("458500") and t.year1_revenue == Decimal("481000")
    assert t.prior_expense == Decimal("137300") and t.year1_expense == Decimal("142000")
    assert t.prior_noi == Decimal("321200") and t.year1_noi == Decimal("339000")


def test_roll_up_removed_row_drops_year_one_keeps_prior() -> None:
    # A row removed from the year-one projection passes year1=0 but keeps its prior (reference).
    lines = [
        GridLine("above", False, Decimal("100"), Decimal("110")),
        GridLine("above", True, Decimal("30"), Decimal("0")),  # expense removed from year one
    ]
    t = roll_up(lines)
    assert t.prior_expense == Decimal("30") and t.year1_expense == Decimal("0")
    assert t.prior_noi == Decimal("70") and t.year1_noi == Decimal("110")


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
    assert row.prior_annual == Decimal("250")  # Jan 100 + Feb 150
    assert row.year1_annual == Decimal("250")  # year-one defaults to prior
    assert row.var_abs == Decimal("0")
    assert doc.totals.year1_revenue == Decimal("250")


async def test_prior_year_seeds_from_annual_om_line(session: AsyncSession) -> None:
    """An OM/annual mapped line (no per-month columns) populates prior-year from its annual amount —
    not just an uploaded recap with JAN/FEB columns."""
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(session, code, "Income")
    # Annual figure with only a provenance key in raw_payload (the shape OM extraction produces).
    session.add(
        FinancialLine(
            line_id=f"fl_{uuid.uuid4().hex[:12]}",
            acquisition_id=acquisition_id,
            period_id=period_id,
            account_code=code,
            account_level=AccountLevel.LEAF,
            amount=Decimal("250000"),
            seller_source_line="Gross Rental Income",
            noi_placement=NoiPlacement.ABOVE,
            raw_payload={"_seller_line": "Gross Rental Income"},
        )
    )
    await session.flush()

    await budget_service.seed_budget(session, acquisition_id)
    doc = await budget_service.get_budget(session, acquisition_id)
    row = next(r for r in doc.rows if r.account_code == code)
    assert row.prior_annual == Decimal("250000")  # from the annual amount, no month buckets
    assert row.year1_annual == Decimal("250000")
    assert doc.totals.year1_revenue == Decimal("250000")


async def test_patch_line_edits_both_columns(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(session, code, "Income")
    await _mapped_line(
        session, acquisition_id, period_id, code, {"JAN 25": "100", "_seller_line": "Rent"}
    )
    await budget_service.seed_budget(session, acquisition_id)

    # Year-one edit flips the override; prior stays the uploaded actual.
    await budget_service.patch_line(
        session,
        acquisition_id,
        BudgetLinePatch(account_code=code, year1_amount=Decimal("500")),
        actor="kurtis",
    )
    row = next(
        r
        for r in (await budget_service.get_budget(session, acquisition_id)).rows
        if r.account_code == code
    )
    assert row.year1_annual == Decimal("500") and row.is_overridden is True
    assert row.prior_annual == Decimal("100") and row.prior_overridden is False

    # Prior is editable too (correct an upload error); the override wins.
    await budget_service.patch_line(
        session,
        acquisition_id,
        BudgetLinePatch(account_code=code, prior_amount=Decimal("120")),
        actor="kurtis",
    )
    row = next(
        r
        for r in (await budget_service.get_budget(session, acquisition_id)).rows
        if r.account_code == code
    )
    assert row.prior_annual == Decimal("120") and row.prior_overridden is True


async def test_add_and_remove_custom_line(session: AsyncSession) -> None:
    acquisition_id, _period_id = await _acquisition(session)
    # A custom revenue line rolls into the year-one revenue total and is flagged for promotion.
    await budget_service.add_line(
        session,
        acquisition_id,
        BudgetLineCreate(
            custom_label="Pickleball fees", section="Income", year1_amount=Decimal("12000")
        ),
        actor="kurtis",
    )
    doc = await budget_service.get_budget(session, acquisition_id)
    row = next(r for r in doc.rows if r.custom_label == "Pickleball fees")
    assert row.account_code is None and row.flagged_for_promotion is True
    assert row.source == "custom" and row.year1_annual == Decimal("12000")
    assert doc.totals.year1_revenue == Decimal("12000")

    # Removing a custom line deletes it outright.
    doc = await budget_service.remove_line(session, acquisition_id, row.line_id, actor="kurtis")
    assert not any(r.custom_label == "Pickleball fees" for r in doc.rows)


async def test_remove_gl_line_keeps_prior_drops_year_one(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(session, code, "Expense")
    await _mapped_line(
        session, acquisition_id, period_id, code, {"JAN 25": "300", "_seller_line": "Repairs"}
    )
    await budget_service.seed_budget(session, acquisition_id)
    line_id = next(
        r.line_id
        for r in (await budget_service.get_budget(session, acquisition_id)).rows
        if r.account_code == code
    )

    doc = await budget_service.remove_line(session, acquisition_id, line_id, actor="kurtis")
    row = next(r for r in doc.rows if r.account_code == code)
    assert row.removed is True
    assert row.prior_annual == Decimal("300")  # prior kept as reference
    assert doc.totals.year1_opex == Decimal("0")  # dropped from year-one


# ── hierarchy + group subtotals (canonical GL tree) ───────────────────────────


async def _group(session: AsyncSession, code: str, name: str, section: str) -> None:
    session.add(
        GLAccount(
            account_code=code,
            level=AccountLevel.SUBGROUP,
            name=name,
            section=section,
            default_noi_placement="above",
            active=True,
        )
    )
    await session.flush()


async def _leaf(
    session: AsyncSession,
    code: str,
    name: str,
    section: str,
    parent: str,
    *,
    is_contra: bool = False,
    tier: str = "core",
) -> None:
    session.add(
        GLAccount(
            account_code=code,
            parent_code=parent,
            level=AccountLevel.LEAF,
            name=name,
            section=section,
            default_noi_placement="above",
            active=True,
            is_contra=is_contra,
            tier=tier,
        )
    )
    await session.flush()


async def test_get_budget_emits_group_subtotals_netting_contra(session: AsyncSession) -> None:
    """A sub-group's subtotal nets its contra child (e.g. Utilities − Recovery), rows carry the
    chart hierarchy (parent_code/tier/is_contra), and only ancestor groups of present rows show."""
    acquisition_id, period_id = await _acquisition(session)
    await _group(session, "605400", "Utilities", "Expense")
    await _leaf(session, "605410", "Electric", "Expense", "605400")
    await _leaf(session, "605415", "Utility Recovery", "Expense", "605400", is_contra=True)
    await _mapped_line(
        session, acquisition_id, period_id, "605410", {"JAN 25": "1000", "_seller_line": "Electric"}
    )
    await _mapped_line(
        session,
        acquisition_id,
        period_id,
        "605415",
        {"JAN 25": "-620", "_seller_line": "Utility Recovery"},
    )
    await budget_service.seed_budget(session, acquisition_id)
    doc = await budget_service.get_budget(session, acquisition_id)

    group = next(g for g in doc.groups if g.code == "605400")
    assert group.prior_annual == Decimal("380")  # 1000 + (−620) net
    assert group.level == "subgroup"
    contra_row = next(r for r in doc.rows if r.account_code == "605415")
    assert contra_row.is_contra is True and contra_row.parent_code == "605400"
    electric_row = next(r for r in doc.rows if r.account_code == "605410")
    assert electric_row.tier == "core" and electric_row.parent_code == "605400"


# ── reorder (drag-to-reorder within a section) ────────────────────────────────


async def test_reorder_persists_section_order(session: AsyncSession) -> None:
    """Dragging line B above line A persists a sort_order so the grid returns them B-then-A."""
    acquisition_id, period_id = await _acquisition(session)
    a = f"a{uuid.uuid4().hex[:8]}"
    b = f"b{uuid.uuid4().hex[:8]}"
    await _account(session, a, "Income")
    await _account(session, b, "Income")
    await _mapped_line(
        session, acquisition_id, period_id, a, {"JAN 25": "100", "_seller_line": "Retail"}
    )
    await _mapped_line(
        session, acquisition_id, period_id, b, {"JAN 25": "200", "_seller_line": "Housekeeping"}
    )
    await budget_service.seed_budget(session, acquisition_id)

    income = [
        r
        for r in (await budget_service.get_budget(session, acquisition_id)).rows
        if r.section == "Income"
    ]
    # Move the second line above the first (drag housekeeping above retail).
    new_order = [income[1], income[0]]
    await budget_service.reorder_lines(
        session,
        acquisition_id,
        [BudgetLineRef(line_id=r.line_id) for r in new_order],
        actor="kurtis",
    )

    after = [
        r
        for r in (await budget_service.get_budget(session, acquisition_id)).rows
        if r.section == "Income"
    ]
    assert [r.account_code for r in after] == [r.account_code for r in new_order]


async def test_reorder_materializes_unseeded_line(session: AsyncSession) -> None:
    """A prior-actuals row not yet stored (line_id None) is materialized when it's dragged."""
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(session, code, "Income")
    await _mapped_line(
        session, acquisition_id, period_id, code, {"JAN 25": "100", "_seller_line": "Rent"}
    )
    # No seed: the row shows as an un-seeded reference (line_id None, account_code set).
    row = next(
        r
        for r in (await budget_service.get_budget(session, acquisition_id)).rows
        if r.account_code == code
    )
    assert row.line_id is None

    await budget_service.reorder_lines(
        session, acquisition_id, [BudgetLineRef(account_code=code)], actor="kurtis"
    )
    row = next(
        r
        for r in (await budget_service.get_budget(session, acquisition_id)).rows
        if r.account_code == code
    )
    assert row.line_id is not None  # now stored
    assert row.prior_annual == Decimal("100")  # provenance/value untouched


async def test_reorder_is_presentational_keeps_noi_and_lock(session: AsyncSession) -> None:
    """Reordering never touches amounts (NOI unchanged) and is allowed on a locked budget."""
    acquisition_id, period_id = await _acquisition(session)
    rev = f"r{uuid.uuid4().hex[:8]}"
    op = f"o{uuid.uuid4().hex[:8]}"
    await _account(session, rev, "Income")
    await _account(session, op, "Expense")
    await _mapped_line(
        session, acquisition_id, period_id, rev, {"JAN 25": "100", "_seller_line": "Rent"}
    )
    await _mapped_line(
        session, acquisition_id, period_id, op, {"JAN 25": "40", "_seller_line": "Utils"}
    )
    await budget_service.seed_budget(session, acquisition_id)
    await budget_service.lock(session, acquisition_id, by="kurtis")
    before = await budget_service.get_budget(session, acquisition_id)
    income = [r for r in before.rows if r.section == "Income"]

    await budget_service.reorder_lines(
        session,
        acquisition_id,
        [BudgetLineRef(line_id=r.line_id) for r in reversed(income)],
        actor="kurtis",
    )
    after = await budget_service.get_budget(session, acquisition_id)
    assert after.status == "locked"  # presentational → lock not invalidated
    assert after.totals.year1_noi == before.totals.year1_noi
    assert after.totals.prior_noi == before.totals.prior_noi


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

    await budget_service.patch_line(
        session,
        acquisition_id,
        BudgetLinePatch(account_code=code, year1_amount=Decimal("999")),
        actor="kurtis",
    )
    assert (await budget_service.get_budget(session, acquisition_id)).status == "draft"


async def test_seed_applies_shield_default(session: AsyncSession) -> None:
    """The defaults engine fills a GL the actuals lack — Shield is a fixed $1,000/mo posted to its
    chart account (600410), superseding any history."""
    acquisition_id, _period_id = await _acquisition(session)
    await _account(session, "600410", "Expense")  # Shield's chart account

    await budget_service.seed_budget(session, acquisition_id)
    doc = await budget_service.get_budget(session, acquisition_id)
    row = next(r for r in doc.rows if r.account_code == "600410")
    assert row.source == "default"
    assert row.year1_annual == Decimal("12000")  # $1,000/mo × 12


async def test_patch_line_rejects_unknown_account(session: AsyncSession) -> None:
    """Editing a GL that isn't in the chart is a 400 (BudgetError), not an FK 500 at commit."""
    acquisition_id, _ = await _acquisition(session)
    with pytest.raises(budget_service.BudgetError):
        await budget_service.patch_line(
            session,
            acquisition_id,
            BudgetLinePatch(account_code="nope", year1_amount=Decimal("5")),
            actor="kurtis",
        )


async def test_readiness_excludes_split_parent(session: AsyncSession) -> None:
    """A split parent (account_code NULL by design) must not count as unmapped, or it would block
    the lock forever."""
    from rjacq.mapping import service as mapping_service
    from rjacq.schemas.financials import MappingSplitPart

    acquisition_id, period_id = await _acquisition(session)
    a1 = f"a{uuid.uuid4().hex[:8]}"
    a2 = f"b{uuid.uuid4().hex[:8]}"
    await _account(session, a1, "Income")
    await _account(session, a2, "Income")
    parent = FinancialLine(
        line_id=f"fl_{uuid.uuid4().hex[:12]}",
        acquisition_id=acquisition_id,
        period_id=period_id,
        seller_source_line="Other Income",
        amount=Decimal("1000"),
    )
    session.add(parent)
    await session.flush()
    await mapping_service.split(
        session,
        line_id=parent.line_id,
        parts=[
            MappingSplitPart(
                account_code=a1,
                account_level=AccountLevel.LEAF,
                amount=Decimal("600"),
                noi_placement=NoiPlacement.ABOVE,
            ),
            MappingSplitPart(
                account_code=a2,
                account_level=AccountLevel.LEAF,
                amount=Decimal("400"),
                noi_placement=NoiPlacement.ABOVE,
            ),
        ],
        confirmed_by="kurtis",
    )

    await budget_service.seed_budget(session, acquisition_id)
    _placeholders, unmapped = await budget_service.readiness(session, acquisition_id)
    assert unmapped == 0  # the container parent is excluded, the mapped children don't count
    await budget_service.lock(session, acquisition_id, by="kurtis")  # not blocked by the parent
    assert (await budget_service.get_budget(session, acquisition_id)).status == "locked"


async def test_partial_manual_override_keeps_locked_opex(session: AsyncSession) -> None:
    """A manual stabilized_revenue with no manual opex keeps the locked-budget opex (not zero)."""
    from rjacq.models.underwriting import ProformaInput
    from rjacq.underwriting import service as uw

    acquisition_id, period_id = await _acquisition(session)
    rev = f"r{uuid.uuid4().hex[:8]}"
    op = f"o{uuid.uuid4().hex[:8]}"
    await _account(session, rev, "Income")
    await _account(session, op, "Expense")
    await _mapped_line(
        session, acquisition_id, period_id, rev, {"JAN 25": "100", "FEB 25": "100", "_s": "Rent"}
    )
    await _mapped_line(
        session, acquisition_id, period_id, op, {"JAN 25": "30", "FEB 25": "30", "_s": "Utils"}
    )
    await budget_service.seed_budget(session, acquisition_id)
    await budget_service.lock(session, acquisition_id, by="kurtis")  # locked stabilized = (200, 60)

    rev_only = ProformaInput(acquisition_id=acquisition_id, stabilized_revenue=Decimal("500"))
    revenue, opex = await uw.effective_stabilized(session, acquisition_id, rev_only)
    assert revenue == Decimal("500") and opex == Decimal("60")  # manual rev + locked opex

    both = ProformaInput(
        acquisition_id=acquisition_id,
        stabilized_revenue=Decimal("500"),
        stabilized_opex=Decimal("99"),
    )
    r2, o2 = await uw.effective_stabilized(session, acquisition_id, both)
    assert r2 == Decimal("500") and o2 == Decimal("99")  # full manual override wins

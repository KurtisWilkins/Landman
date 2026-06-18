"""Underwriting engine tests (design doc §5.5) — worked examples, Decimal money/rates."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import AcquisitionStatus, Phase, PropertyType
from rjacq.models.underwriting import Assumption
from rjacq.underwriting import engine as e
from rjacq.underwriting import repository as repo
from rjacq.underwriting import service as svc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def approx(a: Decimal | None, b: str, tol: str = "1e-6") -> bool:
    assert a is not None
    return abs(a - Decimal(b)) < Decimal(tol)


# ── NOI bridge ──────────────────────────────────────────────────────────────


def test_noi_bridge_excludes_below_line_and_adds_back() -> None:
    lines = [
        e.NoiLine(Decimal("1000000"), "above", is_expense=False),  # revenue
        e.NoiLine(Decimal("400000"), "above", is_expense=True),  # opex
        e.NoiLine(Decimal("84000"), "above", is_expense=True, is_addback=True),  # owner debt svc
        e.NoiLine(Decimal("50000"), "below", is_expense=True),  # below the line — excluded
        e.NoiLine(Decimal("12000"), "non_operating", is_expense=True),  # excluded
    ]
    bridge = e.normalized_noi(lines)
    assert bridge.gross_revenue == Decimal("1000000")
    assert bridge.operating_expense == Decimal("400000")
    assert bridge.addbacks_excluded == Decimal("84000")
    assert bridge.normalized_noi == Decimal("600000")  # 1,000,000 − 400,000 (add-back excluded)


# ── IRR / NPV ───────────────────────────────────────────────────────────────


def test_irr_simple_one_period() -> None:
    assert approx(e.irr([Decimal("-100"), Decimal("110")]), "0.10", "1e-6")


def test_irr_five_year_lump() -> None:
    # 1.1**5 = 1.61051 → IRR is exactly 10%.
    assert approx(e.irr([Decimal("-100"), *([Decimal(0)] * 4), Decimal("161.051")]), "0.10", "1e-6")


def test_irr_none_when_no_sign_change() -> None:
    assert e.irr([Decimal("100"), Decimal("110")]) is None


def test_npv_zero_at_irr() -> None:
    stream = [Decimal("-500"), *([Decimal("140")] * 4), Decimal("1640")]
    r = e.irr(stream)
    assert r is not None
    assert abs(e.npv(r, stream)) < Decimal("1e-6")


# ── Return metrics ──────────────────────────────────────────────────────────


def test_equity_multiple() -> None:
    assert e.equity_multiple(Decimal("100"), [Decimal("10")] * 4 + [Decimal("150")]) == Decimal(
        "1.9"
    )


def test_going_in_cap() -> None:
    assert e.going_in_cap(Decimal("116000"), Decimal("1000000")) == Decimal("0.116")


def test_yr1_cash_on_cash() -> None:
    assert e.yr1_cash_on_cash(Decimal("69"), Decimal("1000")) == Decimal("0.069")


def test_exit_proceeds() -> None:
    gross, net = e.exit_proceeds(Decimal("160000"), Decimal("0.08"), Decimal("1000000"))
    assert gross == Decimal("2000000")  # 160,000 / 0.08
    assert net == Decimal("1000000")  # 2,000,000 − 1,000,000 debt


# ── Hurdles ─────────────────────────────────────────────────────────────────


def test_hurdle_pass_and_fail() -> None:
    assert e.evaluate_hurdle("levered_irr", Decimal("0.194"), Decimal("0.15")).passes is True
    assert e.evaluate_hurdle("yr1_cash_on_cash", Decimal("0.069"), Decimal("0.07")).passes is False


# ── Waterfall (terminal model) ──────────────────────────────────────────────


def _tiers() -> list[e.WaterfallTierInput]:
    return [
        e.WaterfallTierInput(1, Decimal("0"), Decimal("0.08"), Decimal("1.0"), Decimal("0.0")),
        e.WaterfallTierInput(2, Decimal("0.08"), Decimal("0.13"), Decimal("0.8"), Decimal("0.2")),
        e.WaterfallTierInput(3, Decimal("0.13"), None, Decimal("0.7"), Decimal("0.3")),
    ]


def test_waterfall_conserves_cash_and_fills_pref_first() -> None:
    dist = e.distribute_waterfall(
        _tiers(), lp_equity=Decimal("100"), hold_years=5, total_distribution=Decimal("200")
    )
    total_lp = sum(d.lp for d in dist)
    total_gp = sum(d.gp for d in dist)
    # Cash is conserved.
    assert abs((total_lp + total_gp) - Decimal("200")) < Decimal("1e-9")
    # Tier 1 (the preferred band) is LP-only and equals 100·1.08^5.
    assert dist[0].gp == Decimal("0")
    assert abs(dist[0].lp - Decimal("146.93280768")) < Decimal("1e-6")
    # GP only starts earning in the promote bands.
    assert total_gp > 0


def test_waterfall_all_to_lp_when_below_pref() -> None:
    dist = e.distribute_waterfall(
        _tiers(), lp_equity=Decimal("100"), hold_years=5, total_distribution=Decimal("120")
    )
    assert sum(d.gp for d in dist) == Decimal("0")  # never reached the pref ceiling
    assert sum(d.lp for d in dist) == Decimal("120")


# ── Pro forma orchestration ─────────────────────────────────────────────────


def test_build_proforma_worked_example() -> None:
    years = [e.YearInput(Decimal("300"), Decimal("100"), Decimal("50"), Decimal("10"))] * 5
    pf = e.build_proforma(
        years=years,
        equity_basis=Decimal("500"),
        purchase_price=Decimal("2500"),
        exit_cap=Decimal("0.08"),
        debt_payoff=Decimal("1000"),
    )
    assert len(pf.years) == 5
    assert pf.years[0].noi == Decimal("200")  # 300 − 100
    assert pf.years[0].levered_cf == Decimal("140")  # 200 − 50 − 10
    assert pf.exit.gross_value == Decimal("2500")  # 200 / 0.08
    assert pf.exit.net_proceeds == Decimal("1500")  # 2500 − 1000
    assert pf.equity_multiple == Decimal("4.4")  # (140·4 + 1640) / 500
    assert pf.going_in_cap == Decimal("0.08")  # 200 / 2500
    assert pf.yr1_cash_on_cash == Decimal("0.28")  # 140 / 500
    # IRR is self-consistent (NPV at IRR ≈ 0).
    assert pf.levered_irr is not None
    stream = [Decimal("-500"), *([Decimal("140")] * 4), Decimal("1640")]
    assert abs(e.npv(pf.levered_irr, stream)) < Decimal("1e-6")


# ── persistence + endpoints (real Postgres) ─────────────────────────────────


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _make_acquisition(session: AsyncSession) -> str:
    acquisition_id = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Acquisition(
            acquisition_id=acquisition_id,
            name="Underwriting Test Park",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
        )
    )
    await session.flush()
    return acquisition_id


async def test_store_and_get_proforma_roundtrip(session: AsyncSession) -> None:
    acquisition_id = await _make_acquisition(session)
    years = [e.YearInput(Decimal("300"), Decimal("100"), Decimal("50"), Decimal("10"))] * 5
    output = e.build_proforma(
        years=years,
        equity_basis=Decimal("500"),
        purchase_price=Decimal("2500"),
        exit_cap=Decimal("0.08"),
        debt_payoff=Decimal("1000"),
    )
    await svc.store_proforma(session, acquisition_id, output)
    await session.commit()

    results = await svc.get_proforma(session, acquisition_id)
    assert len(results.years) == 5
    assert results.years[0].noi == Decimal("200")
    assert results.equity_multiple == Decimal("4.4")
    assert results.exit is not None
    assert results.exit.net_proceeds == Decimal("1500")


async def test_override_assumption_records_provenance(session: AsyncSession) -> None:
    acquisition_id = await _make_acquisition(session)
    session.add(
        Assumption(
            assumption_id=f"as_{uuid.uuid4().hex[:12]}",
            acquisition_id=acquisition_id,
            key="stabilized_occupancy",
            label="Stabilized occupancy",
            baseline_value=Decimal("0.60"),
            shield_source="portfolio_rv_t12",
            is_overridden=False,
        )
    )
    await session.flush()

    await svc.override_assumption(
        session,
        acquisition_id,
        key="stabilized_occupancy",
        override_value=Decimal("0.55"),
        note="Tougher shoulder season here",
        author="kurtis",
    )
    await session.commit()

    a = await repo.get_assumption(session, acquisition_id, "stabilized_occupancy")
    assert a is not None
    assert a.baseline_value == Decimal("0.60")  # baseline retained (provenance)
    assert a.override_value == Decimal("0.55")
    assert a.is_overridden is True
    assert a.overridden_by == "kurtis"
    assert a.note == "Tougher shoulder season here"


async def test_override_missing_assumption_raises(session: AsyncSession) -> None:
    acquisition_id = await _make_acquisition(session)
    with pytest.raises(svc.UnderwritingError) as ei:
        await svc.override_assumption(
            session,
            acquisition_id,
            key="nope",
            override_value=Decimal("1"),
            note=None,
            author="kurtis",
        )
    assert ei.value.code == "assumption_not_found"

"""Promote-waterfall engine tests (pure math; worked example + edge cases).

The default scenario must reproduce the "Waterfall Template" spreadsheet's returns within
rounding tolerance — this is the correctness-critical regression (CLAUDE.md: underwriting math
ships with worked examples).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from rjacq.underwriting.promote import (
    PromoteInputs,
    build_dates,
    eomonth,
    moic,
    run_promote_waterfall,
    xirr,
)

PCT = Decimal("0.001")  # 0.1% IRR tolerance
USD = Decimal("1")


def approx(a: Decimal | None, b: str, tol: Decimal) -> bool:
    assert a is not None
    return abs(a - Decimal(b)) <= tol


# ── primitives ──────────────────────────────────────────────────────────────


def test_eomonth_and_dates() -> None:
    assert eomonth(date(2025, 12, 31), 12) == date(2026, 12, 31)
    assert eomonth(date(2025, 1, 31), 12) == date(2026, 1, 31)
    dates = build_dates(date(2025, 12, 31), 5)
    assert dates[0] == date(2025, 12, 31)
    assert dates[-1] == date(2030, 12, 31)
    assert len(dates) == 6


def test_xirr_and_moic_basics() -> None:
    # 100 out, 110 back in one year ≈ 10%.
    d0, d1 = date(2025, 1, 1), date(2026, 1, 1)
    assert approx(xirr([Decimal("-100"), Decimal("110")], [d0, d1]), "0.10", Decimal("0.002"))
    assert xirr([Decimal("1"), Decimal("2")], [d0, d1]) is None  # no sign change → no IRR
    assert moic([Decimal("-100"), Decimal("250")]) == Decimal("2.5")


# ── worked example: the spreadsheet defaults ─────────────────────────────────


def test_default_scenario_matches_spreadsheet() -> None:
    r = run_promote_waterfall(PromoteInputs())

    # Purchase price = equity / (1 − LTV).
    assert approx(r.purchase_price, "428571428.57", USD)

    # Returns summary (Acquisition-Level 18.6%/2.23x · Partner 17.5%/2.13x · RJourney 27.6%/3.19x).
    assert approx(r.acquisition.irr, "0.18639", PCT)
    assert approx(r.acquisition.moic, "2.2339", Decimal("0.001"))
    assert approx(r.partner.irr, "0.17450", PCT)
    assert approx(r.partner.moic, "2.1271", Decimal("0.001"))
    assert approx(r.rjourney.irr, "0.27599", PCT)
    assert approx(r.rjourney.moic, "3.1948", Decimal("0.001"))

    # Equity contributed.
    assert approx(r.rjourney.equity, "15000000", USD)
    assert approx(r.partner.equity, "135000000", USD)

    # Profit by position + total promote.
    assert approx(r.rjourney.profit, "32922203.89", Decimal("100"))
    assert approx(r.partner.profit, "152163780.49", Decimal("100"))
    assert approx(r.total_promote, "16015117.17", Decimal("100"))

    # Waterfall reconciles to acquisition profit.
    assert r.cashflow_ties_out

    # Tier bands: H1 (8%) and H2 (15%) fully clear; H3/H4 (20%) do not bind at an 18.6% IRR.
    assert r.tiers[0].binds and approx(r.tiers[0].irr_check, "0.08", PCT)
    assert r.tiers[1].binds and approx(r.tiers[1].irr_check, "0.15", PCT)
    assert not r.tiers[2].binds
    assert not r.tiers[3].binds
    assert approx(r.tiers[0].equity_total, "63622050.26", Decimal("100"))
    assert approx(r.tiers[1].carry_total, "8277669.66", Decimal("100"))


def test_partner_plus_rjourney_reconciles_to_acquisition() -> None:
    r = run_promote_waterfall(PromoteInputs())
    # Partner + RJourney profit ties to total acquisition profit (acq fee = 0 here).
    total = r.partner.profit + r.rjourney.profit
    assert approx(total, str(r.acquisition.profit), Decimal("100"))


# ── edge cases ───────────────────────────────────────────────────────────────


def test_zero_promote_gives_no_carry_and_equal_position_irrs() -> None:
    inp = PromoteInputs(promotes=(Decimal(0), Decimal(0), Decimal(0), Decimal(0)))
    r = run_promote_waterfall(inp)
    assert r.total_promote == 0
    assert all(t.carry_total == 0 for t in r.tiers)
    # With no promote, both positions are pure pari-passu → identical IRR/MOIC.
    assert r.partner.irr is not None and r.rjourney.irr is not None
    assert abs(r.partner.irr - r.rjourney.irr) < PCT
    assert r.cashflow_ties_out


def test_downside_only_first_hurdle_binds() -> None:
    # A modest exit → acquisition IRR sits just above hurdle 1; upper tiers don't bind.
    inp = PromoteInputs(
        cashflow_override=(
            Decimal("-150000000"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("230000000"),  # ~8.9% over 5 yrs
        )
    )
    r = run_promote_waterfall(inp)
    assert r.acquisition.irr is not None and Decimal("0.08") < r.acquisition.irr < Decimal("0.15")
    assert r.tiers[0].binds  # 8% hurdle clears
    assert r.tiers[2].carry_total == 0 and r.tiers[3].carry_total == 0  # 20% tiers never reached
    assert r.cashflow_ties_out


def test_acquisition_and_management_fees_flow_to_rjourney() -> None:
    base = run_promote_waterfall(PromoteInputs())
    withfees = run_promote_waterfall(
        PromoteInputs(acquisition_fee_pct=Decimal("0.01"), mgmt_fee_pct=Decimal("0.005"))
    )
    # Fees lift RJourney's take and reduce the Partner's, vs. the no-fee base.
    assert withfees.rjourney.profit > base.rjourney.profit
    assert withfees.partner.profit < base.partner.profit
    assert approx(withfees.acquisition_fee, str(withfees.purchase_price * Decimal("0.01")), USD)

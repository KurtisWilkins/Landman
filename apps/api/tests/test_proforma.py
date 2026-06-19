"""Pro-forma engine tests: debt amortization, GL-line NOI projection, and assembly.

Pure math (no DB). Worked examples are hand-checkable so the financing + projection logic is
correctness-pinned (CLAUDE.md: underwriting math ships with worked examples).
"""

from __future__ import annotations

from decimal import Decimal

from rjacq.underwriting.proforma import (
    DebtTerms,
    GLLine,
    ProformaInputs,
    build_acquisition_proforma,
    project_lines,
    size_debt,
)


def approx(a: Decimal, b: str, tol: str = "1") -> bool:
    return abs(a - Decimal(b)) <= Decimal(tol)


# ── debt sizing ───────────────────────────────────────────────────────────────


def test_size_debt_zero_rate_amortizes_linearly() -> None:
    # 0% rate, no IO, 360-mo amort, 5-yr hold: monthly = loan/360; balance = loan·300/360.
    terms = DebtTerms(ltv=Decimal("0.65"), annual_rate=Decimal("0"), amort_months=360, io_years=0)
    sched = size_debt(Decimal("10000000"), terms, hold_years=5)
    assert sched.loan_amount == Decimal("6500000")
    # 60 monthly payments of loan/360 each.
    assert approx(sum(sched.annual_debt_service, Decimal(0)), str(Decimal("6500000") * 60 / 360))
    # 300 of 360 months remain unpaid.
    assert approx(sched.balance_at_exit, str(Decimal("6500000") * 300 / 360))


def test_size_debt_interest_only_keeps_principal() -> None:
    # IO covers the whole hold: balance unchanged, debt service = annual interest on the full loan.
    terms = DebtTerms(
        ltv=Decimal("0.60"), annual_rate=Decimal("0.06"), amort_months=360, io_years=5
    )
    sched = size_debt(Decimal("10000000"), terms, hold_years=5)
    assert sched.loan_amount == Decimal("6000000")
    assert approx(sched.balance_at_exit, "6000000")
    # Each IO year ≈ 6% of 6,000,000 = 360,000 (monthly compounding makes it marginally higher).
    for ds in sched.annual_debt_service:
        assert Decimal("360000") <= ds <= Decimal("372000")


def test_size_debt_amortizing_pays_down_principal() -> None:
    terms = DebtTerms(
        ltv=Decimal("0.65"), annual_rate=Decimal("0.065"), amort_months=360, io_years=0
    )
    sched = size_debt(Decimal("10000000"), terms, hold_years=5)
    # Some principal is paid down, but most of a 30-yr loan remains after 5 yrs.
    assert sched.balance_at_exit < sched.loan_amount
    assert sched.balance_at_exit > Decimal("6000000")


# ── NOI projection ─────────────────────────────────────────────────────────────


def test_project_lines_grows_each_line() -> None:
    lines = [
        GLLine("Site revenue", Decimal("1000000"), is_expense=False),
        GLLine("Payroll", Decimal("400000"), is_expense=True),
    ]
    rows = project_lines(lines, noi_growth=Decimal("0.03"), hold_years=3)
    assert len(rows) == 3
    assert rows[0] == (Decimal("1000000"), Decimal("400000"))  # year 1 = stabilized
    rev2, opex2 = rows[1]
    assert approx(rev2, "1030000") and approx(opex2, "412000")  # +3%


def test_project_lines_per_line_growth_override() -> None:
    lines = [
        GLLine("Site revenue", Decimal("1000000"), is_expense=False, growth=Decimal("0.05")),
        GLLine("Payroll", Decimal("400000"), is_expense=True),  # uses global 0.03
    ]
    rows = project_lines(lines, noi_growth=Decimal("0.03"), hold_years=2)
    rev2, opex2 = rows[1]
    assert approx(rev2, "1050000")  # 5% override
    assert approx(opex2, "412000")  # 3% global


# ── assembly ────────────────────────────────────────────────────────────────────


def test_build_acquisition_proforma_ties_together() -> None:
    inp = ProformaInputs(
        purchase_price=Decimal("10000000"),
        hold_years=5,
        lines=[
            GLLine("Revenue", Decimal("1200000"), is_expense=False),
            GLLine("OpEx", Decimal("500000"), is_expense=True),
        ],
        noi_growth=Decimal("0.03"),
        exit_cap=Decimal("0.07"),
        debt=DebtTerms(
            ltv=Decimal("0.65"), annual_rate=Decimal("0.065"), amort_months=360, io_years=2
        ),
        selling_cost_rate=Decimal("0.02"),
    )
    result = build_acquisition_proforma(inp)
    # Equity = price - loan = 10,000,000 - 6,500,000.
    assert result.equity_basis == Decimal("3500000")
    # Year-1 NOI = 1,200,000 - 500,000 = 700,000; going-in cap = 700,000 / 10,000,000 = 7%.
    assert approx(result.proforma.going_in_cap * 100, "7", tol="0.01")
    # Stream is hold_years + 1 long, opens with -equity, and produces a real IRR.
    assert len(result.equity_cashflows) == 6
    assert result.equity_cashflows[0] == Decimal("-3500000")
    assert result.proforma.levered_irr is not None

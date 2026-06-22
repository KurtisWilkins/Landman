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
    build_monthly_cashflows,
    monthly_debt_schedule,
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


# ── 60-month cash flow ───────────────────────────────────────────────────────────


def _monthly_inputs() -> ProformaInputs:
    return ProformaInputs(
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
        capex_reserve_rate=Decimal("0.01"),
    )


def test_monthly_debt_schedule_matches_size_debt() -> None:
    """The monthly schedule summed in 12-month blocks reproduces size_debt's annual figures and
    the exit balance — the refactor that keeps the two debt views reconciled."""
    inp = _monthly_inputs()
    monthly, balance = monthly_debt_schedule(inp.purchase_price, inp.debt, inp.hold_years)
    sched = size_debt(inp.purchase_price, inp.debt, inp.hold_years)
    assert len(monthly) == 60
    assert balance == sched.balance_at_exit  # exact
    for yr in range(5):
        assert sum(monthly[yr * 12 : (yr + 1) * 12]) == sched.annual_debt_service[yr]  # exact


def test_build_monthly_cashflows_rolls_up_to_annual() -> None:
    """Each 12-month block rolls up to the matching annual pro-forma row (the regression guard for
    decision: feed the waterfall an annual rollup of the monthly grid)."""
    inp = _monthly_inputs()
    annual = build_acquisition_proforma(inp).proforma.years
    monthly = build_monthly_cashflows(inp)
    assert len(monthly) == 60
    for yr, row in enumerate(annual):
        block = monthly[yr * 12 : (yr + 1) * 12]
        assert approx(sum(r.revenue for r in block), str(row.revenue), tol="0.01")
        assert approx(sum(r.opex for r in block), str(row.opex), tol="0.01")
        assert approx(sum(r.noi for r in block), str(row.noi), tol="0.01")
        assert sum(r.debt_service for r in block) == row.debt_service  # exact
        assert approx(sum(r.capex for r in block), str(row.capex), tol="0.01")
        assert approx(sum(r.levered_cf for r in block), str(row.levered_cf), tol="0.01")


def test_build_monthly_cashflows_spreads_year_evenly() -> None:
    inp = _monthly_inputs()
    monthly = build_monthly_cashflows(inp)
    # Year 1 = stabilized 1,200,000 revenue spread evenly → 100,000/mo for the first 12 months.
    for row in monthly[:12]:
        assert approx(row.revenue, "100000", tol="0.01")
    assert monthly[0].month == 1 and monthly[-1].month == 60


def test_monthly_debt_schedule_io_then_amortizes() -> None:
    # 2-yr IO: the first 24 months are level interest-only; month 25 adds principal (higher).
    terms = DebtTerms(
        ltv=Decimal("0.65"), annual_rate=Decimal("0.06"), amort_months=360, io_years=2
    )
    monthly, _ = monthly_debt_schedule(Decimal("10000000"), terms, hold_years=5)
    io = monthly[:24]
    assert all(ds == io[0] for ds in io)  # interest-only is constant (balance unchanged)
    assert monthly[24] > monthly[23]  # amortization begins → payment includes principal

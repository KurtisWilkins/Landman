"""Acquisition pro forma (pure): size debt, project NOI on the RJourney GL structure, and
assemble the levered equity cash-flow stream that feeds the promote.

Decimal throughout (never float for money/rates). Nothing here decides a business value — the
purchase price, financing terms, growth, and exit cap are passed in (the caller reads them from
the acquisition + the configurable underwriting defaults). The functions are deterministic and
unit-tested with worked examples. Reuses ``engine.build_proforma`` for the cash-flow/IRR math.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext

from .engine import ProformaOutput, YearInput, build_proforma

getcontext().prec = 40

ZERO = Decimal(0)
ONE = Decimal(1)


# ── inputs ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GLLine:
    """A stabilized (year-1) line on the RJourney GL chart. ``growth`` overrides the deal-level
    NOI growth for this line when set (manual control); otherwise the global growth applies."""

    label: str
    amount: Decimal  # year-1 stabilized amount, positive
    is_expense: bool
    growth: Decimal | None = None


@dataclass(frozen=True)
class DebtTerms:
    ltv: Decimal
    annual_rate: Decimal
    amort_months: int
    io_years: int = 0


@dataclass(frozen=True)
class ProformaInputs:
    purchase_price: Decimal
    hold_years: int
    lines: list[GLLine]
    noi_growth: Decimal  # default per-year growth for lines without their own
    exit_cap: Decimal
    debt: DebtTerms
    selling_cost_rate: Decimal = ZERO
    capex_reserve_rate: Decimal = ZERO  # fraction of revenue reserved as CapEx each year


# ── outputs ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DebtSchedule:
    loan_amount: Decimal
    annual_debt_service: list[Decimal]  # one entry per hold year
    balance_at_exit: Decimal


@dataclass(frozen=True)
class AcquisitionProforma:
    debt: DebtSchedule
    equity_basis: Decimal  # purchase price minus loan
    proforma: ProformaOutput  # years + exit + IRR/MOIC (from engine.build_proforma)
    equity_cashflows: list[Decimal]  # [-equity, levered CF…, +net exit] — feeds the promote


# ── debt sizing (amortizing, optional interest-only period) ────────────────────


def size_debt(purchase_price: Decimal, terms: DebtTerms, hold_years: int) -> DebtSchedule:
    """Loan = price·LTV. Interest-only for ``io_years``, then a level payment that amortizes the
    balance over the remaining amortization term. Returns annual debt service per hold year and
    the principal still outstanding at exit (the payoff).
    """
    loan = purchase_price * terms.ltv
    mr = terms.annual_rate / Decimal(12)
    io_months = terms.io_years * 12
    amort_after_io = terms.amort_months - io_months
    if amort_after_io <= 0:
        raise ValueError("amortization term must exceed the interest-only period")

    if mr == 0:
        amort_payment = loan / Decimal(amort_after_io)
    else:
        amort_payment = loan * mr / (ONE - (ONE + mr) ** (-amort_after_io))

    balance = loan
    annual: list[Decimal] = []
    for yr in range(hold_years):
        ds = ZERO
        for month in range(12):
            global_m = yr * 12 + month
            interest = balance * mr
            if global_m < io_months:
                ds += interest  # interest-only: no principal paydown
                continue
            principal = amort_payment - interest
            if principal > balance:  # final partial period
                principal = balance
            balance -= principal
            ds += interest + principal
        annual.append(ds)
    return DebtSchedule(loan_amount=loan, annual_debt_service=annual, balance_at_exit=balance)


# ── NOI projection on the GL structure ─────────────────────────────────────────


def project_lines(
    lines: list[GLLine], noi_growth: Decimal, hold_years: int
) -> list[tuple[Decimal, Decimal]]:
    """Grow each GL line across the hold (its own growth, else the deal-level NOI growth).
    Returns ``[(revenue, opex), …]`` per year — revenue = sum of income lines, opex = sum of
    expense lines."""
    out: list[tuple[Decimal, Decimal]] = []
    for yr in range(hold_years):
        revenue = ZERO
        opex = ZERO
        for line in lines:
            g = line.growth if line.growth is not None else noi_growth
            amount = line.amount * (ONE + g) ** yr
            if line.is_expense:
                opex += amount
            else:
                revenue += amount
        out.append((revenue, opex))
    return out


# ── orchestration ──────────────────────────────────────────────────────────────


def build_acquisition_proforma(inp: ProformaInputs) -> AcquisitionProforma:
    """Project NOI, size debt, and assemble the levered equity cash-flow stream + metrics."""
    if inp.hold_years < 1:
        raise ValueError("hold_years must be >= 1")
    projected = project_lines(inp.lines, inp.noi_growth, inp.hold_years)
    debt = size_debt(inp.purchase_price, inp.debt, inp.hold_years)

    years = [
        YearInput(
            revenue=rev,
            opex=opex,
            debt_service=debt.annual_debt_service[i],
            capex=rev * inp.capex_reserve_rate,
        )
        for i, (rev, opex) in enumerate(projected)
    ]
    equity_basis = inp.purchase_price - debt.loan_amount
    out = build_proforma(
        years=years,
        equity_basis=equity_basis,
        purchase_price=inp.purchase_price,
        exit_cap=inp.exit_cap,
        debt_payoff=debt.balance_at_exit,
        selling_cost_rate=inp.selling_cost_rate,
    )

    # Equity cash-flow stream for the promote: t0 outflow, levered CF per year, net exit in yr N.
    stream = [-equity_basis] + [row.levered_cf for row in out.years]
    stream[-1] += out.exit.net_proceeds
    return AcquisitionProforma(
        debt=debt, equity_basis=equity_basis, proforma=out, equity_cashflows=stream
    )


# Re-exported for callers that build line lists from mapped financials.
__all__ = [
    "GLLine",
    "DebtTerms",
    "ProformaInputs",
    "DebtSchedule",
    "AcquisitionProforma",
    "size_debt",
    "project_lines",
    "build_acquisition_proforma",
]

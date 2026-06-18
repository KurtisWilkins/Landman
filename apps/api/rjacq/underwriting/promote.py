"""Deal-by-deal promote waterfall engine (pure, testable).

Reconstructs the "Waterfall Template" spreadsheet's JV promote math: a deal-level cash-flow
stream is run through return-of-capital, then four sequential IRR-hurdle tiers with a promote
"tier-shift" split, and finally split into the two equity positions — **Partner Equity** and
**RJourney Equity** — plus a deal-level reference return.

Money is ``Decimal`` throughout (CLAUDE.md: never float for financial values). Dates are annual
(EOMONTH +12 from the start); preferred return accrues actual/365 and returns are date-based
(XIRR), matching the sheet. This module is UI- and DB-free so the math can be unit-tested
against the spreadsheet's worked example.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, getcontext

# Financial math needs headroom for the bisection/power operations (matches underwriting/engine).
getcontext().prec = 50

_ZERO = Decimal(0)
_ONE = Decimal(1)


# ── inputs ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExitAssumptions:
    """Year-N exit, reproducing the sheet's bespoke reversion exactly:

    ``terminal = ((last_operating_dist + base_value*income_yield) / cap_rate - base_value)
    + last_operating_dist*(1+growth)``. The three constants are hardcoded in the sheet; here
    they are named, editable parameters with the sheet's defaults.
    """

    cap_rate: Decimal = Decimal("0.05")
    base_value: Decimal = Decimal("300000000")
    income_yield: Decimal = Decimal("0.07")


@dataclass(frozen=True)
class PromoteInputs:
    deal_name: str = "Deal 1"
    start_date: date = field(default_factory=lambda: date(2025, 12, 31))
    hold_years: int = 5
    equity: Decimal = Decimal("150000000")
    ltv: Decimal = Decimal("0.65")
    acquisition_fee_pct: Decimal = _ZERO  # paid to RJourney: purchase_price * pct, at year 0
    mgmt_fee_pct: Decimal = _ZERO  # annual, accrues on cumulative invested capital, to RJourney
    rjourney_coinvest_pct: Decimal = Decimal("0.10")
    yr1_distribution_pct: Decimal = Decimal("0.05")
    distribution_growth: Decimal = Decimal("0.05")
    exit: ExitAssumptions = field(default_factory=ExitAssumptions)
    hurdles: tuple[Decimal, ...] = (
        Decimal("0.08"),
        Decimal("0.15"),
        Decimal("0.20"),
        Decimal("0.20"),
    )
    promotes: tuple[Decimal, ...] = (
        Decimal("0.10"),
        Decimal("0.20"),
        Decimal("0.30"),
        Decimal("0.30"),
    )
    # Optional manual override of the deal-level cash-flow stream (len hold_years+1); when set,
    # the generator (yr1%/growth/exit) is bypassed entirely.
    cashflow_override: tuple[Decimal, ...] | None = None


# ── results ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TierResult:
    tier: int
    hurdle_rate: Decimal
    promote_pct: Decimal  # RJourney share of cash clearing into the next tier
    equity_distributions: list[Decimal]  # per period (>=0)
    carried_interest: list[Decimal]  # per period (>=0)
    equity_total: Decimal
    carry_total: Decimal
    irr_check: Decimal | None  # XIRR of the tier's investor stream
    binds: bool  # True if the tier is fully cleared (its IRR check ties to the hurdle)


@dataclass(frozen=True)
class PositionReturn:
    label: str
    cashflows: list[Decimal]
    equity: Decimal  # contributed (>=0)
    profit: Decimal  # net gain
    irr: Decimal | None
    moic: Decimal | None


@dataclass(frozen=True)
class PromoteResult:
    deal_name: str
    dates: list[date]
    purchase_price: Decimal
    acquisition_fee: Decimal
    deal_cashflows: list[Decimal]
    combined_equity_distributions: list[Decimal]
    rjourney_carried_interest: list[Decimal]
    total_promote: Decimal
    tiers: list[TierResult]
    deal: PositionReturn
    partner: PositionReturn
    rjourney: PositionReturn
    cashflow_ties_out: bool  # combined equity + carry reconciles to deal profit


# ── primitives ──────────────────────────────────────────────────────────────────


def eomonth(d: date, months: int) -> date:
    """Last day of the month ``months`` after ``d`` (Excel EOMONTH)."""
    total = (d.year * 12 + (d.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1).replace(day=1)
        from datetime import timedelta

        last = last - timedelta(days=1)
    return last


def build_dates(start: date, years: int) -> list[date]:
    dates = [start]
    for _ in range(years):
        dates.append(eomonth(dates[-1], 12))
    return dates


def xirr(cashflows: list[Decimal], dates: list[date]) -> Decimal | None:
    """Date-based IRR (actual/365) via bisection; None if no sign change / no root."""
    if len(cashflows) != len(dates) or not cashflows:
        return None
    if not (any(c > 0 for c in cashflows) and any(c < 0 for c in cashflows)):
        return None
    t0 = dates[0]
    fracs = [Decimal((d - t0).days) / Decimal(365) for d in dates]

    def npv(rate: Decimal) -> Decimal:
        base = _ONE + rate
        return sum((cf / (base**f) for cf, f in zip(cashflows, fracs, strict=True)), _ZERO)

    lo, hi = Decimal("-0.9999"), Decimal("10")
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < Decimal("1e-9"):
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def moic(cashflows: list[Decimal]) -> Decimal | None:
    inflow = sum((c for c in cashflows if c > 0), _ZERO)
    outflow = sum((c for c in cashflows if c < 0), _ZERO)
    if outflow == 0:
        return None
    return -inflow / outflow


def generate_cashflows(inp: PromoteInputs) -> list[Decimal]:
    """Deal-level CF[0..hold_years]: −equity, then growing distributions, then exit + final."""
    if inp.cashflow_override is not None:
        return list(inp.cashflow_override)
    g = inp.distribution_growth
    cf = [-inp.equity, inp.equity * inp.yr1_distribution_pct]
    for _ in range(2, inp.hold_years):
        cf.append(cf[-1] * (_ONE + g))
    last_op = cf[-1]  # final-year operating distribution is grown off the prior year
    ex = inp.exit
    reversion = (last_op + ex.base_value * ex.income_yield) / ex.cap_rate - ex.base_value
    cf.append(reversion + last_op * (_ONE + g))
    return cf


# ── engine ──────────────────────────────────────────────────────────────────────


def run_promote_waterfall(inp: PromoteInputs) -> PromoteResult:  # noqa: PLR0915 (faithful, linear)
    n = inp.hold_years
    dates = build_dates(inp.start_date, n)
    cf = generate_cashflows(inp)
    purchase_price = inp.equity / (_ONE - inp.ltv)
    acq_fee = purchase_price * inp.acquisition_fee_pct

    dist = [max(x, _ZERO) for x in cf]  # distributions out of the deal (>=0)
    invested = [min(x, _ZERO) for x in cf]  # capital in (<=0)
    contribution = [-x for x in invested]  # (>=0)

    # Return of capital (sheet rows 56–61): distributions first repay the capital balance.
    roc = [_ZERO] * (n + 1)
    cum_invested = [_ZERO] * (n + 1)
    bop = _ZERO
    running = _ZERO
    for k in range(n + 1):
        running += contribution[k]
        cum_invested[k] = running
        avail = bop + contribution[k]
        roc[k] = -min(dist[k], avail)  # negative
        bop = avail + roc[k]
    residual = [max(_ZERO, cf[k] + roc[k]) for k in range(n + 1)]  # row 61, into the waterfall

    # Annual management fee accrues on cumulative invested capital (row 70), paid to RJourney.
    mgmt = [_ZERO] * (n + 1)
    for k in range(1, n + 1):
        mgmt[k] = cum_invested[k] * inp.mgmt_fee_pct

    day_frac = [_ZERO] * (n + 1)
    for k in range(1, n + 1):
        day_frac[k] = Decimal((dates[k] - dates[k - 1]).days) / Decimal(365)

    # Four sequential hurdle tiers. Tier t fills equity with factor (1 − P_{t-1}) and books
    # RJourney carry on the cash that clears into the next tier; tier 1 has no promote.
    hurdle_eq_dists: list[list[Decimal]] = []
    tiers: list[TierResult] = []
    residual_in = residual
    for t in range(1, len(inp.hurdles) + 1):
        rate = inp.hurdles[t - 1]
        promote = _ZERO if t == 1 else inp.promotes[t - 2]
        eq_dist = [_ZERO] * (n + 1)
        carry = [_ZERO] * (n + 1)
        resid_out = [_ZERO] * (n + 1)
        inv_cf = [_ZERO] * (n + 1)
        eop = _ZERO
        for k in range(n + 1):
            bop = eop
            accrual = ((_ONE + rate) ** day_frac[k] - _ONE) * bop if k >= 1 else _ZERO
            prior_fills = sum((hd[k] for hd in hurdle_eq_dists), _ZERO)  # negative
            balance = bop + contribution[k] + mgmt[k] + accrual + roc[k] + prior_fills
            target = residual_in[k] * (_ONE - promote)
            d = -max(min(target, balance), _ZERO)  # distribution (negative)
            eq_dist[k] = d
            if promote > 0:
                carry[k] = d / (_ONE - promote) * promote  # negative
            eop = max(balance + d, _ZERO)
            resid_out[k] = max(residual_in[k] + d + carry[k], _ZERO)
            # Investor stream for the tier IRR check: capital in, then RoC + fills up to this
            # tier, less management fees (sheet rows 75/100/124/148).
            inv_cf[k] = invested[k] - roc[k] - prior_fills - d - mgmt[k]
        check = xirr(inv_cf, dates)
        binds = check is not None and abs(check - rate) < Decimal("1e-4")
        tiers.append(
            TierResult(
                tier=t,
                hurdle_rate=rate,
                promote_pct=promote,
                equity_distributions=[-x for x in eq_dist],
                carried_interest=[-x for x in carry],
                equity_total=sum((-x for x in eq_dist), _ZERO),
                carry_total=sum((-x for x in carry), _ZERO),
                irr_check=check,
                binds=binds,
            )
        )
        hurdle_eq_dists.append(eq_dist)
        residual_in = resid_out

    # Residual above the top hurdle (rows 162–163).
    p_resid = inp.promotes[-1]
    resid_equity = [residual_in[k] * (_ONE - p_resid) for k in range(n + 1)]
    resid_carry = [residual_in[k] * p_resid for k in range(n + 1)]

    # Cash-flow summary (rows 166–167): combined equity + RJourney carry.
    combined_equity = [
        resid_equity[k] + sum((-hd[k] for hd in hurdle_eq_dists), _ZERO) for k in range(n + 1)
    ]
    rjourney_carry = [resid_carry[k] + tiers_carry(tiers, k) for k in range(n + 1)]
    total_promote = sum(rjourney_carry, _ZERO)

    # Position split (rows 178–220).
    coinvest = inp.rjourney_coinvest_pct
    partner_pct = _ONE - coinvest
    inflows = [combined_equity[k] + rjourney_carry[k] for k in range(n + 1)]
    # Combined investor stream, net of fees + carry paid to RJourney (rows 178–184).
    gross_inv = [
        invested[k] + inflows[k] + (-roc[k]) - mgmt[k] - rjourney_carry[k] for k in range(n + 1)
    ]
    partner_cf = [partner_pct * gross_inv[k] for k in range(n + 1)]
    rjourney_cf = [
        coinvest * gross_inv[k] + mgmt[k] + rjourney_carry[k] + (acq_fee if k == 0 else _ZERO)
        for k in range(n + 1)
    ]

    deal = _position("Deal-Level", cf, dates)
    partner = _position("Partner Equity", partner_cf, dates)
    rjourney = _position("RJourney Equity", rjourney_cf, dates)

    deal_profit_check = sum(combined_equity, _ZERO) + total_promote
    ties = abs(deal_profit_check - sum(cf, _ZERO)) < Decimal("1")

    return PromoteResult(
        deal_name=inp.deal_name,
        dates=dates,
        purchase_price=purchase_price,
        acquisition_fee=acq_fee,
        deal_cashflows=cf,
        combined_equity_distributions=combined_equity,
        rjourney_carried_interest=rjourney_carry,
        total_promote=total_promote,
        tiers=tiers,
        deal=deal,
        partner=partner,
        rjourney=rjourney,
        cashflow_ties_out=ties,
    )


def tiers_carry(tiers: list[TierResult], k: int) -> Decimal:
    return sum((t.carried_interest[k] for t in tiers), _ZERO)


def _position(label: str, cashflows: list[Decimal], dates: list[date]) -> PositionReturn:
    equity = sum((-c for c in cashflows if c < 0), _ZERO)
    profit = sum(cashflows, _ZERO)
    return PositionReturn(
        label=label,
        cashflows=cashflows,
        equity=equity,
        profit=profit,
        irr=xirr(cashflows, dates),
        moic=moic(cashflows),
    )

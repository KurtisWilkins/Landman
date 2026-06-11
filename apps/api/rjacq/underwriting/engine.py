"""Pure underwriting math (design doc §5.5). Decimal only — never float for money/rates.

Nothing here decides a business value: thresholds, splits, financing terms, and the
waterfall structure are passed in (the caller reads them from per-deal data + config). The
functions are deterministic and unit-tested with worked examples.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, getcontext

# Generous precision for iterative root-finding; outputs are quantized by callers.
getcontext().prec = 40

ZERO = Decimal(0)
ONE = Decimal(1)


# ── NOI bridge (§5.3.7 / §5.5) ──────────────────────────────────────────────


@dataclass(frozen=True)
class NoiLine:
    """A normalized financial line for the NOI bridge.

    ``noi_placement`` ∈ {above, below, non_operating}. ``is_expense`` distinguishes OpEx
    from revenue. ``is_addback`` marks owner/one-time items excluded from operating expense
    (e.g. owner debt service) — they are added back to NOI.
    """

    amount: Decimal
    noi_placement: str
    is_expense: bool
    is_addback: bool = False


@dataclass(frozen=True)
class NoiBridge:
    gross_revenue: Decimal
    operating_expense: Decimal
    addbacks_excluded: Decimal
    normalized_noi: Decimal


def normalized_noi(lines: Sequence[NoiLine]) -> NoiBridge:
    """Compute normalized NOI: above-the-line revenue minus above-the-line operating
    expense, excluding below-the-line / non-operating lines and adding back owner/one-time
    items (§5.3.7).
    """
    revenue = ZERO
    opex = ZERO
    addbacks = ZERO
    for line in lines:
        if line.noi_placement != "above":
            continue  # below-the-line + non-operating are excluded from NOI
        if not line.is_expense:
            revenue += line.amount
        elif line.is_addback:
            addbacks += line.amount  # excluded from opex (added back)
        else:
            opex += line.amount
    return NoiBridge(
        gross_revenue=revenue,
        operating_expense=opex,
        addbacks_excluded=addbacks,
        normalized_noi=revenue - opex,
    )


# ── Time-value: NPV / IRR ───────────────────────────────────────────────────


def npv(rate: Decimal, cashflows: Sequence[Decimal]) -> Decimal:
    """NPV of ``cashflows`` (index 0 = t0) at ``rate`` per period."""
    total = ZERO
    factor = ONE
    discount = ONE + rate
    for cf in cashflows:
        total += cf / factor
        factor *= discount
    return total


def irr(cashflows: Sequence[Decimal], *, tol: Decimal = Decimal("1e-9")) -> Decimal | None:
    """Internal rate of return for a cashflow stream (index 0 = t0), via bisection.

    Returns None when there is no sign change (no real IRR in range). Bisection keeps this
    Decimal-exact and avoids float; the typical deal has one outflow then inflows.
    """
    if not cashflows or all(cf >= 0 for cf in cashflows) or all(cf <= 0 for cf in cashflows):
        return None
    low, high = Decimal("-0.9999"), Decimal("10")  # -99.99% .. 1000%
    f_low = npv(low, cashflows)
    f_high = npv(high, cashflows)
    if f_low * f_high > 0:
        return None  # root not bracketed in the search range
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = npv(mid, cashflows)
        if abs(f_mid) < tol:
            return mid
        if f_low * f_mid < 0:
            high = mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2


# ── Return metrics ──────────────────────────────────────────────────────────


def equity_multiple(equity: Decimal, distributions: Sequence[Decimal]) -> Decimal:
    """Total distributions ÷ equity invested (a.k.a. MOIC). ``equity`` > 0."""
    if equity <= 0:
        raise ValueError("equity must be positive")
    return sum(distributions, ZERO) / equity


def going_in_cap(year1_noi: Decimal, purchase_price: Decimal) -> Decimal:
    if purchase_price <= 0:
        raise ValueError("purchase_price must be positive")
    return year1_noi / purchase_price


def yr1_cash_on_cash(year1_levered_cf: Decimal, equity: Decimal) -> Decimal:
    if equity <= 0:
        raise ValueError("equity must be positive")
    return year1_levered_cf / equity


def exit_proceeds(
    exit_noi: Decimal, exit_cap: Decimal, debt_payoff: Decimal, selling_cost_rate: Decimal = ZERO
) -> tuple[Decimal, Decimal]:
    """(gross_value, net_proceeds) at sale. gross = NOI / cap; net = gross·(1−cost) − debt."""
    if exit_cap <= 0:
        raise ValueError("exit_cap must be positive")
    gross = exit_noi / exit_cap
    net = gross * (ONE - selling_cost_rate) - debt_payoff
    return gross, net


# ── Hurdles ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HurdleResult:
    metric: str
    threshold: Decimal
    actual: Decimal
    passes: bool


def evaluate_hurdle(metric: str, actual: Decimal, threshold: Decimal) -> HurdleResult:
    """A hurdle passes when actual ≥ threshold (all current metrics are 'higher is better')."""
    return HurdleResult(
        metric=metric, threshold=threshold, actual=actual, passes=actual >= threshold
    )


# ── Equity waterfall (terminal-distribution model) ──────────────────────────


@dataclass(frozen=True)
class WaterfallTierInput:
    tier: int
    irr_floor: Decimal
    irr_ceiling: Decimal | None  # None = top (residual) tier
    lp_split: Decimal
    gp_split: Decimal


@dataclass(frozen=True)
class TierDistribution:
    tier: int
    lp: Decimal
    gp: Decimal


def distribute_waterfall(
    tiers: Sequence[WaterfallTierInput],
    *,
    lp_equity: Decimal,
    hold_years: int,
    total_distribution: Decimal,
) -> list[TierDistribution]:
    """Split a single terminal distribution across IRR-band tiers (European waterfall).

    Modeling assumption (documented): one terminal distribution at ``hold_years``. Each tier
    is an LP-IRR band; cash fills bands in order, capping the LP's cumulative take at the
    band ceiling ``lp_equity·(1+ceiling)^hold`` per its ``lp_split``. The residual (top) tier
    has no ceiling. Catch-up and return-of-capital structural variants are unresolved
    (§14 A-2) and are NOT assumed here — they are added as explicit parameters when decided.

    Interim-cashflow waterfalls are a later refinement; the deal-level levered IRR/equity
    multiple above already use the full cashflow timeline.
    """
    remaining = total_distribution
    lp_cumulative = ZERO
    out: list[TierDistribution] = []
    for t in sorted(tiers, key=lambda x: x.tier):
        if remaining <= 0:
            out.append(TierDistribution(tier=t.tier, lp=ZERO, gp=ZERO))
            continue
        if t.irr_ceiling is None:
            # Residual tier: split everything that remains.
            lp = remaining * t.lp_split
            gp = remaining * t.gp_split
            out.append(TierDistribution(tier=t.tier, lp=lp, gp=gp))
            lp_cumulative += lp
            remaining = ZERO
            continue
        # LP's cumulative target at this band's ceiling.
        lp_target = lp_equity * ((ONE + t.irr_ceiling) ** hold_years)
        lp_needed = lp_target - lp_cumulative
        if lp_needed <= 0:
            out.append(TierDistribution(tier=t.tier, lp=ZERO, gp=ZERO))
            continue
        # Distribution that delivers lp_needed to LP at this band's split (a GP-only band
        # with lp_split 0 would never advance LP's IRR, so it consumes the remainder).
        band_total = remaining if t.lp_split <= 0 else lp_needed / t.lp_split
        band_total = min(band_total, remaining)
        lp = band_total * t.lp_split
        gp = band_total * t.gp_split
        out.append(TierDistribution(tier=t.tier, lp=lp, gp=gp))
        lp_cumulative += lp
        remaining -= band_total
    return out


# ── Pro forma orchestration (§5.5) ──────────────────────────────────────────


@dataclass(frozen=True)
class YearInput:
    revenue: Decimal
    opex: Decimal
    debt_service: Decimal
    capex: Decimal


@dataclass(frozen=True)
class ProformaYear:
    yr: int
    revenue: Decimal
    opex: Decimal
    noi: Decimal
    debt_service: Decimal
    capex: Decimal
    levered_cf: Decimal


@dataclass(frozen=True)
class ProformaExit:
    year: int
    exit_cap: Decimal
    gross_value: Decimal
    net_proceeds: Decimal


@dataclass(frozen=True)
class ProformaOutput:
    years: list[ProformaYear]
    exit: ProformaExit
    levered_irr: Decimal | None
    equity_multiple: Decimal
    going_in_cap: Decimal
    yr1_cash_on_cash: Decimal
    equity_basis: Decimal


def build_proforma(
    *,
    years: Sequence[YearInput],
    equity_basis: Decimal,
    purchase_price: Decimal,
    exit_cap: Decimal,
    debt_payoff: Decimal,
    selling_cost_rate: Decimal = ZERO,
) -> ProformaOutput:
    """Assemble the 5-yr levered cash flow and metrics from explicit yearly inputs + an exit.

    All inputs are supplied by the caller (built from the deal's assumptions/financials and
    config-provided financing terms); this function decides nothing.
    """
    if not years:
        raise ValueError("at least one year is required")
    rows: list[ProformaYear] = []
    for i, y in enumerate(years, start=1):
        noi = y.revenue - y.opex
        lcf = noi - y.debt_service - y.capex
        rows.append(
            ProformaYear(
                yr=i,
                revenue=y.revenue,
                opex=y.opex,
                noi=noi,
                debt_service=y.debt_service,
                capex=y.capex,
                levered_cf=lcf,
            )
        )

    hold = len(rows)
    exit_noi = rows[-1].noi
    gross, net = exit_proceeds(exit_noi, exit_cap, debt_payoff, selling_cost_rate)
    exit_row = ProformaExit(year=hold, exit_cap=exit_cap, gross_value=gross, net_proceeds=net)

    # Cashflow stream for IRR: t0 outflow, then levered CF each year, net exit added in year N.
    stream = [-equity_basis] + [r.levered_cf for r in rows]
    stream[-1] += net
    distributions = [r.levered_cf for r in rows]
    distributions[-1] += net

    return ProformaOutput(
        years=rows,
        exit=exit_row,
        levered_irr=irr(stream),
        equity_multiple=equity_multiple(equity_basis, distributions),
        going_in_cap=going_in_cap(rows[0].noi, purchase_price),
        yr1_cash_on_cash=yr1_cash_on_cash(rows[0].levered_cf, equity_basis),
        equity_basis=equity_basis,
    )

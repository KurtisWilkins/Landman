"""Promote-waterfall calculator endpoint (§9).

Stateless what-if tool: POST the inputs, get the full deal-by-deal promote result back. No
persistence — it's an interactive calculator. The math lives in ``underwriting/promote.py`` (a
pure, unit-tested module); this router only marshals types.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.auth import Principal, get_current_principal
from ..schemas.promote import PositionOut, PromoteRequest, PromoteResponse, TierOut
from ..underwriting import promote as engine

router = APIRouter(tags=["promote"])


def _position(p: engine.PositionReturn) -> PositionOut:
    return PositionOut(
        label=p.label,
        cashflows=p.cashflows,
        equity=p.equity,
        profit=p.profit,
        irr=p.irr,
        moic=p.moic,
    )


@router.post("/promote/waterfall", response_model=PromoteResponse)
async def compute_promote_waterfall(
    body: PromoteRequest,
    _principal: Principal = Depends(get_current_principal),
) -> PromoteResponse:
    """Run the deal-by-deal promote waterfall and return both equity positions + the breakdown."""
    inp = engine.PromoteInputs(
        deal_name=body.deal_name,
        start_date=body.start_date,
        hold_years=body.hold_years,
        equity=body.equity,
        ltv=body.ltv,
        acquisition_fee_pct=body.acquisition_fee_pct,
        mgmt_fee_pct=body.mgmt_fee_pct,
        rjourney_coinvest_pct=body.rjourney_coinvest_pct,
        yr1_distribution_pct=body.yr1_distribution_pct,
        distribution_growth=body.distribution_growth,
        exit=engine.ExitAssumptions(
            cap_rate=body.exit.cap_rate,
            base_value=body.exit.base_value,
            income_yield=body.exit.income_yield,
        ),
        hurdles=tuple(body.hurdles),
        promotes=tuple(body.promotes),
        cashflow_override=tuple(body.cashflow_override) if body.cashflow_override else None,
    )
    r = engine.run_promote_waterfall(inp)
    return PromoteResponse(
        deal_name=r.deal_name,
        dates=r.dates,
        purchase_price=r.purchase_price,
        acquisition_fee=r.acquisition_fee,
        deal_cashflows=r.deal_cashflows,
        combined_equity_distributions=r.combined_equity_distributions,
        rjourney_carried_interest=r.rjourney_carried_interest,
        total_promote=r.total_promote,
        tiers=[
            TierOut(
                tier=t.tier,
                hurdle_rate=t.hurdle_rate,
                promote_pct=t.promote_pct,
                equity_total=t.equity_total,
                carry_total=t.carry_total,
                irr_check=t.irr_check,
                binds=t.binds,
            )
            for t in r.tiers
        ],
        deal=_position(r.deal),
        partner=_position(r.partner),
        rjourney=_position(r.rjourney),
        cashflow_ties_out=r.cashflow_ties_out,
    )

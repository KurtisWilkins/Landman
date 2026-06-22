"""Underwriting service: assemble/persist pro forma; record assumption overrides.

Recompute-on-change uses the pure engine. The projection from assumptions to yearly lines
and the default financing terms are unresolved decisions (§14 A-1..A-4) and are NOT invented
here; until a acquisition carries a stored pro forma (computed by ingestion/SHIELD once those land),
an override records provenance and returns the current pro forma without fabricating numbers.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..models.acquisitions import Acquisition
from ..models.underwriting import ProformaInput
from ..schemas.underwriting import (
    AcquisitionReturns,
    ProformaExit,
    ProformaMonth,
    ProformaMonthlyResults,
    ProformaResults,
    ProformaYear,
)
from . import promote as promote_engine
from . import repository as repo
from .engine import ProformaOutput
from .proforma import (
    DebtTerms,
    GLLine,
    ProformaInputs,
    build_acquisition_proforma,
    build_monthly_cashflows,
)

_ONE = Decimal(1)

log = get_logger("underwriting")

_ZERO = Decimal(0)
# Financing/exit/hold inputs that must all be present before a pro forma can be computed.
# Leverage is checked separately (an LTV *or* a dollar loan_amount satisfies it). Stabilized
# revenue/opex are handled separately too: they fall back to the GL-mapped P&L's NOI bridge
# (extraction-first), so they aren't required to be entered manually.
_REQUIRED_FIN = ("exit_cap", "loan_rate", "amort_months", "hold_years")


async def noi_bridge_totals(session: AsyncSession, acquisition_id: str) -> tuple[Decimal, Decimal]:
    """Stabilized revenue + operating expense from the acquisition's GL-mapped P&L (NOI bridge).
    Zeros until a P&L is uploaded and mapped. Lazy import avoids an import cycle with mapping."""
    from ..mapping import noi as noi_mapping

    bridge = await noi_mapping.noi_bridge_for_acquisition(session, acquisition_id)
    return bridge.gross_revenue, bridge.operating_expense


async def effective_stabilized(
    session: AsyncSession, acquisition_id: str, inp: ProformaInput | None
) -> tuple[Decimal | None, Decimal | None]:
    """Stabilized revenue/opex to use: the manually-saved values, else the NOI-bridge totals from
    the GL-mapped P&L (extraction-first). A bridge with no revenue stays None (no fabrication)."""
    bridge_rev, bridge_opex = await noi_bridge_totals(session, acquisition_id)
    saved_rev = inp.stabilized_revenue if inp is not None else None
    saved_opex = inp.stabilized_opex if inp is not None else None
    revenue = saved_rev if saved_rev is not None else (bridge_rev if bridge_rev > 0 else None)
    opex = saved_opex if saved_opex is not None else (bridge_opex if revenue is not None else None)
    return revenue, opex


class UnderwritingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def get_proforma(session: AsyncSession, acquisition_id: str) -> ProformaResults:
    """Assemble the §9 ProformaResults from persisted results + summary (read-only)."""
    rows = await repo.get_results(session, acquisition_id)
    summary = await repo.get_summary(session, acquisition_id)
    years = [
        ProformaYear(
            yr=r.yr,
            revenue=r.revenue,
            opex=r.opex,
            noi=r.noi,
            debt_service=r.debt_service,
            capex=r.capex,
            levered_cf=r.levered_cf,
        )
        for r in rows
    ]
    exit_block = None
    if summary is not None and summary.exit_year is not None:
        exit_block = ProformaExit(
            year=summary.exit_year,
            exit_cap=summary.exit_cap,
            gross_value=summary.exit_gross_value,
            net_proceeds=summary.exit_net_proceeds,
        )
    return ProformaResults(
        years=years,
        exit=exit_block,
        levered_irr=summary.levered_irr if summary else None,
        equity_multiple=summary.equity_multiple if summary else None,
        equity_basis=summary.equity_basis if summary else None,
    )


async def get_proforma_monthly(
    session: AsyncSession, acquisition_id: str
) -> ProformaMonthlyResults:
    """The persisted 60-month cash-flow grid (read-only; empty until a pro forma is computed)."""
    rows = await repo.get_proforma_monthly(session, acquisition_id)
    return ProformaMonthlyResults(months=[ProformaMonth.model_validate(r) for r in rows])


async def store_proforma(
    session: AsyncSession, acquisition_id: str, output: ProformaOutput
) -> None:
    """Persist a computed pro forma (used by the recompute path and tests)."""
    await repo.replace_proforma(session, acquisition_id, output)
    log.info("underwriting.proforma_stored", acquisition_id=acquisition_id)


async def get_inputs(session: AsyncSession, acquisition_id: str) -> ProformaInput | None:
    return await repo.get_proforma_input(session, acquisition_id)


async def _purchase_price(session: AsyncSession, acquisition_id: str) -> Decimal | None:
    """The price that flows downstream: the negotiated purchase price, else the OM ask."""
    acquisition = await session.get(Acquisition, acquisition_id)
    if acquisition is None:
        return None
    return (
        acquisition.purchase_price
        if acquisition.purchase_price is not None
        else acquisition.ask_price
    )


async def save_inputs_and_recompute(
    session: AsyncSession, acquisition_id: str, fields: dict[str, object]
) -> ProformaResults:
    """Save the acquisition's pro-forma inputs, recompute + persist the pro forma when the
    inputs (and a purchase price) are complete, and return the current results. Never fabricates
    numbers: if a required input is missing, the inputs are saved but no pro forma is computed.
    """
    inp = await repo.upsert_proforma_input(session, acquisition_id, fields)
    price = await _purchase_price(session, acquisition_id)
    revenue, opex = await effective_stabilized(session, acquisition_id, inp)
    fin_present = all(getattr(inp, k) is not None for k in _REQUIRED_FIN)
    leverage_present = inp.ltv is not None or inp.loan_amount is not None
    ready = (
        price is not None
        and revenue is not None
        and revenue > 0
        and fin_present
        and leverage_present
    )
    if ready:
        assert price is not None and revenue is not None  # narrowed by `ready`
        # Leverage: a dollar loan_amount override wins; otherwise size_debt uses the LTV. The
        # override is expressed as an effective LTV (loan / price) so the pure engine is unchanged.
        effective_ltv = inp.ltv or _ZERO
        if inp.loan_amount is not None and price > 0:
            effective_ltv = inp.loan_amount / price
        engine_inputs = ProformaInputs(
            purchase_price=price,
            hold_years=int(inp.hold_years or 0),
            lines=[
                GLLine("Revenue", revenue, is_expense=False, growth=inp.revenue_growth),
                GLLine("OpEx", opex or _ZERO, is_expense=True, growth=inp.expense_growth),
            ],
            noi_growth=inp.noi_growth or _ZERO,
            exit_cap=inp.exit_cap or _ZERO,
            debt=DebtTerms(
                ltv=effective_ltv,
                annual_rate=inp.loan_rate or _ZERO,
                amort_months=int(inp.amort_months or 0),
                io_years=int(inp.io_years or 0),
            ),
            selling_cost_rate=inp.selling_cost_rate or _ZERO,
            capex_reserve_rate=inp.capex_reserve_rate or _ZERO,
        )
        result = build_acquisition_proforma(engine_inputs)
        await store_proforma(session, acquisition_id, result.proforma)
        await repo.replace_proforma_monthly(
            session, acquisition_id, build_monthly_cashflows(engine_inputs)
        )
    await session.commit()
    return await get_proforma(session, acquisition_id)


async def acquisition_returns(session: AsyncSession, acquisition_id: str) -> AcquisitionReturns:
    """Headline returns from the persisted pro forma run through the promote. Promote terms come
    from the acquisition's canonical inputs (co-invest, fees, start date) and its persisted
    waterfall_tiers (hurdles/promotes) when set; any unset term falls back to the engine default,
    so an acquisition that has never customized its promote is byte-identical to the standard
    waterfall. Empty until a pro forma is computed."""
    pf = await get_proforma(session, acquisition_id)
    if not pf.years or pf.equity_basis is None:
        return AcquisitionReturns()

    equity = pf.equity_basis
    stream = [-equity, *[(y.levered_cf or _ZERO) for y in pf.years]]
    if pf.exit is not None and pf.exit.net_proceeds is not None:
        stream[-1] += pf.exit.net_proceeds

    price = await _purchase_price(session, acquisition_id)
    ltv = (_ONE - equity / price) if (price is not None and price > equity) else _ZERO

    # Promote terms: persisted per-acquisition values win; anything unset uses the engine default
    # (defaults() is the single source so we never duplicate the [DECISION] hurdle/split literals).
    inp = await repo.get_proforma_input(session, acquisition_id)
    promote_defaults = promote_engine.PromoteInputs()
    coinvest = promote_defaults.rjourney_coinvest_pct
    acq_fee = promote_defaults.acquisition_fee_pct
    mgmt_fee = promote_defaults.mgmt_fee_pct
    start = promote_defaults.start_date
    if inp is not None:
        if inp.rjourney_coinvest_pct is not None:
            coinvest = inp.rjourney_coinvest_pct
        if inp.acquisition_fee_pct is not None:
            acq_fee = inp.acquisition_fee_pct
        if inp.mgmt_fee_pct is not None:
            mgmt_fee = inp.mgmt_fee_pct
        if inp.start_date is not None:
            start = inp.start_date
    tiers = await repo.get_waterfall_tiers(session, acquisition_id)
    if tiers:
        hurdles = tuple(t.irr_floor or _ZERO for t in tiers)
        promotes = tuple(t.gp_split or _ZERO for t in tiers)
    else:
        hurdles = promote_defaults.hurdles
        promotes = promote_defaults.promotes

    result = promote_engine.run_promote_waterfall(
        promote_engine.PromoteInputs(
            equity=equity,
            hold_years=len(pf.years),
            ltv=ltv,
            cashflow_override=tuple(stream),
            rjourney_coinvest_pct=coinvest,
            acquisition_fee_pct=acq_fee,
            mgmt_fee_pct=mgmt_fee,
            start_date=start,
            hurdles=hurdles,
            promotes=promotes,
        )
    )

    year1_noi = pf.years[0].noi
    going_in_cap = (
        (year1_noi / price) if (price is not None and price > 0 and year1_noi is not None) else None
    )
    loan = (price - equity) if price is not None else None
    return AcquisitionReturns(
        going_in_cap=going_in_cap,
        loan_amount=loan,
        ltv=(loan / price) if (loan is not None and price) else None,
        hold_years=len(pf.years),
        equity=equity,
        promote_value=result.total_promote,
        partner_irr=result.partner.irr,
        partner_moic=result.partner.moic,
        rjourney_irr=result.rjourney.irr,
        rjourney_moic=result.rjourney.moic,
        deal_irr=result.acquisition.irr,
        deal_moic=result.acquisition.moic,
    )


async def override_assumption(
    session: AsyncSession,
    acquisition_id: str,
    *,
    key: str,
    override_value: Decimal,
    note: str | None,
    author: str,
) -> ProformaResults:
    """Record an assumption override with provenance (baseline retained), then return the
    current pro forma. A full recompute runs once the acquisition carries the inputs needed to
    project yearly lines (unresolved A-1..A-4); we never fabricate them here.
    """
    assumption = await repo.get_assumption(session, acquisition_id, key)
    if assumption is None:
        raise UnderwritingError(
            "assumption_not_found", f"No assumption '{key}' for this acquisition."
        )
    # Provenance: baseline_value is untouched; the override + author + note are recorded.
    assumption.override_value = override_value
    assumption.is_overridden = True
    assumption.overridden_by = author
    assumption.note = note
    await session.flush()
    log.info(
        "underwriting.assumption_overridden", acquisition_id=acquisition_id, key=key, by=author
    )
    return await get_proforma(session, acquisition_id)

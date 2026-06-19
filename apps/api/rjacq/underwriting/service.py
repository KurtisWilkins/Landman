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
    ProformaExit,
    ProformaResults,
    ProformaYear,
)
from . import repository as repo
from .engine import ProformaOutput
from .proforma import DebtTerms, GLLine, ProformaInputs, build_acquisition_proforma

log = get_logger("underwriting")

_ZERO = Decimal(0)
# Inputs that must all be present (plus a purchase price) before a pro forma can be computed.
_REQUIRED_INPUTS = (
    "stabilized_revenue",
    "stabilized_opex",
    "exit_cap",
    "ltv",
    "loan_rate",
    "amort_months",
    "hold_years",
)


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
    ready = price is not None and all(getattr(inp, k) is not None for k in _REQUIRED_INPUTS)
    if ready:
        assert price is not None  # narrowed by `ready`; for the type checker
        engine_inputs = ProformaInputs(
            purchase_price=price,
            hold_years=int(inp.hold_years or 0),
            lines=[
                GLLine("Revenue", inp.stabilized_revenue or _ZERO, is_expense=False),
                GLLine("OpEx", inp.stabilized_opex or _ZERO, is_expense=True),
            ],
            noi_growth=inp.noi_growth or _ZERO,
            exit_cap=inp.exit_cap or _ZERO,
            debt=DebtTerms(
                ltv=inp.ltv or _ZERO,
                annual_rate=inp.loan_rate or _ZERO,
                amort_months=int(inp.amort_months or 0),
                io_years=int(inp.io_years or 0),
            ),
            selling_cost_rate=inp.selling_cost_rate or _ZERO,
            capex_reserve_rate=inp.capex_reserve_rate or _ZERO,
        )
        result = build_acquisition_proforma(engine_inputs)
        await store_proforma(session, acquisition_id, result.proforma)
    await session.commit()
    return await get_proforma(session, acquisition_id)


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

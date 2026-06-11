"""Underwriting service: assemble/persist pro forma; record assumption overrides.

Recompute-on-change uses the pure engine. The projection from assumptions to yearly lines
and the default financing terms are unresolved decisions (§14 A-1..A-4) and are NOT invented
here; until a deal carries a stored pro forma (computed by ingestion/SHIELD once those land),
an override records provenance and returns the current pro forma without fabricating numbers.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..schemas.underwriting import (
    ProformaExit,
    ProformaResults,
    ProformaYear,
)
from . import repository as repo
from .engine import ProformaOutput

log = get_logger("underwriting")


class UnderwritingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def get_proforma(session: AsyncSession, deal_id: str) -> ProformaResults:
    """Assemble the §9 ProformaResults from persisted results + summary (read-only)."""
    rows = await repo.get_results(session, deal_id)
    summary = await repo.get_summary(session, deal_id)
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


async def store_proforma(session: AsyncSession, deal_id: str, output: ProformaOutput) -> None:
    """Persist a computed pro forma (used by ingestion/SHIELD recompute paths and tests)."""
    await repo.replace_proforma(session, deal_id, output)
    log.info("underwriting.proforma_stored", deal_id=deal_id)


async def override_assumption(
    session: AsyncSession,
    deal_id: str,
    *,
    key: str,
    override_value: Decimal,
    note: str | None,
    author: str,
) -> ProformaResults:
    """Record an assumption override with provenance (baseline retained), then return the
    current pro forma. A full recompute runs once the deal carries the inputs needed to
    project yearly lines (unresolved A-1..A-4); we never fabricate them here.
    """
    assumption = await repo.get_assumption(session, deal_id, key)
    if assumption is None:
        raise UnderwritingError("assumption_not_found", f"No assumption '{key}' for this deal.")
    # Provenance: baseline_value is untouched; the override + author + note are recorded.
    assumption.override_value = override_value
    assumption.is_overridden = True
    assumption.overridden_by = author
    assumption.note = note
    await session.flush()
    log.info("underwriting.assumption_overridden", deal_id=deal_id, key=key, by=author)
    return await get_proforma(session, deal_id)

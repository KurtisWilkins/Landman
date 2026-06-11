"""Repository for underwriting persistence (DB access only)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.underwriting import Assumption, ProformaResult, ProformaSummary
from .engine import ProformaOutput


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def get_results(session: AsyncSession, deal_id: str) -> Sequence[ProformaResult]:
    stmt = (
        select(ProformaResult).where(ProformaResult.deal_id == deal_id).order_by(ProformaResult.yr)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_summary(session: AsyncSession, deal_id: str) -> ProformaSummary | None:
    return await session.get(ProformaSummary, deal_id)


async def get_assumption(session: AsyncSession, deal_id: str, key: str) -> Assumption | None:
    stmt = select(Assumption).where(Assumption.deal_id == deal_id, Assumption.key == key)
    return (await session.execute(stmt)).scalars().first()


async def replace_proforma(session: AsyncSession, deal_id: str, output: ProformaOutput) -> None:
    """Persist a freshly-computed pro forma: replace the year rows and the summary."""
    await session.execute(delete(ProformaResult).where(ProformaResult.deal_id == deal_id))
    for row in output.years:
        session.add(
            ProformaResult(
                result_id=_new_id("pr"),
                deal_id=deal_id,
                yr=row.yr,
                revenue=row.revenue,
                opex=row.opex,
                noi=row.noi,
                debt_service=row.debt_service,
                capex=row.capex,
                levered_cf=row.levered_cf,
            )
        )
    summary = await session.get(ProformaSummary, deal_id)
    irr_val: Decimal | None = output.levered_irr
    if summary is None:
        summary = ProformaSummary(deal_id=deal_id)
        session.add(summary)
    summary.levered_irr = irr_val
    summary.equity_multiple = output.equity_multiple
    summary.equity_basis = output.equity_basis
    summary.exit_year = output.exit.year
    summary.exit_cap = output.exit.exit_cap
    summary.exit_gross_value = output.exit.gross_value
    summary.exit_net_proceeds = output.exit.net_proceeds
    await session.flush()

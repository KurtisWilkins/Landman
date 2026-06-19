"""Repository for underwriting persistence (DB access only)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.underwriting import Assumption, ProformaInput, ProformaResult, ProformaSummary
from .engine import ProformaOutput


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def get_results(session: AsyncSession, acquisition_id: str) -> Sequence[ProformaResult]:
    stmt = (
        select(ProformaResult)
        .where(ProformaResult.acquisition_id == acquisition_id)
        .order_by(ProformaResult.yr)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_summary(session: AsyncSession, acquisition_id: str) -> ProformaSummary | None:
    return await session.get(ProformaSummary, acquisition_id)


async def get_assumption(session: AsyncSession, acquisition_id: str, key: str) -> Assumption | None:
    stmt = select(Assumption).where(
        Assumption.acquisition_id == acquisition_id, Assumption.key == key
    )
    return (await session.execute(stmt)).scalars().first()


async def get_proforma_input(session: AsyncSession, acquisition_id: str) -> ProformaInput | None:
    return await session.get(ProformaInput, acquisition_id)


async def upsert_proforma_input(
    session: AsyncSession, acquisition_id: str, fields: dict[str, object]
) -> ProformaInput:
    """Create or update the acquisition's pro-forma inputs; only provided fields are applied."""
    obj = await session.get(ProformaInput, acquisition_id)
    if obj is None:
        obj = ProformaInput(acquisition_id=acquisition_id)
        session.add(obj)
    for key, value in fields.items():
        setattr(obj, key, value)
    await session.flush()
    return obj


async def replace_proforma(
    session: AsyncSession, acquisition_id: str, output: ProformaOutput
) -> None:
    """Persist a freshly-computed pro forma: replace the year rows and the summary."""
    await session.execute(
        delete(ProformaResult).where(ProformaResult.acquisition_id == acquisition_id)
    )
    for row in output.years:
        session.add(
            ProformaResult(
                result_id=_new_id("pr"),
                acquisition_id=acquisition_id,
                yr=row.yr,
                revenue=row.revenue,
                opex=row.opex,
                noi=row.noi,
                debt_service=row.debt_service,
                capex=row.capex,
                levered_cf=row.levered_cf,
            )
        )
    summary = await session.get(ProformaSummary, acquisition_id)
    irr_val: Decimal | None = output.levered_irr
    if summary is None:
        summary = ProformaSummary(acquisition_id=acquisition_id)
        session.add(summary)
    summary.levered_irr = irr_val
    summary.equity_multiple = output.equity_multiple
    summary.equity_basis = output.equity_basis
    summary.exit_year = output.exit.year
    summary.exit_cap = output.exit.exit_cap
    summary.exit_gross_value = output.exit.gross_value
    summary.exit_net_proceeds = output.exit.net_proceeds
    await session.flush()

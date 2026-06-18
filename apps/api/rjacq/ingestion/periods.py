"""Financial-period (upload version) lifecycle (§5.2, §8.4).

Each P&L upload is a dated, retained version of a acquisition's financials. Exactly one is *current*
(feeds the GL/mapping view); the rest stay queryable as history. Activation only flips the
``is_current`` flag — no version is ever deleted (append-never-overwrite; provenance is sacred).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.financials import FinancialLine, FinancialPeriod


async def list_periods(
    session: AsyncSession, acquisition_id: str
) -> Sequence[tuple[FinancialPeriod, int]]:
    """All upload versions for a acquisition (newest first) with their line counts."""
    stmt = (
        select(FinancialPeriod, func.count(FinancialLine.line_id))
        .outerjoin(FinancialLine, FinancialLine.period_id == FinancialPeriod.period_id)
        .where(FinancialPeriod.acquisition_id == acquisition_id)
        .group_by(FinancialPeriod.period_id)
        .order_by(FinancialPeriod.ingested_at.desc())
    )
    return [(period, count) for period, count in (await session.execute(stmt)).all()]


async def activate_period(session: AsyncSession, acquisition_id: str, period_id: str) -> bool:
    """Make ``period_id`` the current version for the acquisition. Returns False if it isn't this
    acquisition's period. Demotes the others (UPDATE only — nothing is deleted)."""
    period = await session.get(FinancialPeriod, period_id)
    if period is None or period.acquisition_id != acquisition_id:
        return False
    await session.execute(
        update(FinancialPeriod)
        .where(
            FinancialPeriod.acquisition_id == acquisition_id, FinancialPeriod.is_current.is_(True)
        )
        .values(is_current=False)
    )
    await session.execute(
        update(FinancialPeriod)
        .where(FinancialPeriod.period_id == period_id)
        .values(is_current=True)
    )
    return True

"""Repository for the mapping engine (DB access only)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.financials import FinancialLine, FinancialPeriod
from ..models.reference import GLAccount, GLMappingLearned


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def current_period_id(session: AsyncSession, acquisition_id: str) -> str | None:
    """The acquisition's active financial version: the current one, else the most recent upload."""
    stmt = (
        select(FinancialPeriod.period_id)
        .where(FinancialPeriod.acquisition_id == acquisition_id)
        .order_by(FinancialPeriod.is_current.desc(), FinancialPeriod.ingested_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def shortlist_accounts(
    session: AsyncSession, query_vec: list[float], k: int = 5
) -> list[tuple[GLAccount, float]]:
    """Top-k gl_accounts by cosine similarity to ``query_vec`` (pgvector)."""
    distance = GLAccount.embedding.cosine_distance(query_vec)
    stmt = (
        select(GLAccount, distance.label("distance"))
        .where(GLAccount.embedding.isnot(None), GLAccount.active.is_(True))
        .order_by(distance)
        .limit(k)
    )
    rows = (await session.execute(stmt)).all()
    return [(acc, 1.0 - float(dist)) for acc, dist in rows]  # similarity = 1 − cosine distance


async def get_account(session: AsyncSession, account_code: str) -> GLAccount | None:
    return await session.get(GLAccount, account_code)


async def list_accounts(session: AsyncSession) -> Sequence[GLAccount]:
    """All active GL accounts in canonical order (the mapping picker + review name lookup)."""
    stmt = (
        select(GLAccount)
        .where(GLAccount.active.is_(True))
        .order_by(GLAccount.sort, GLAccount.account_code)
    )
    return (await session.execute(stmt)).scalars().all()


async def find_learned(
    session: AsyncSession, *, seller_phrase: str, source_seller: str | None
) -> GLMappingLearned | None:
    """Exact learned mapping for a seller's phrasing (§5.3.5)."""
    stmt = select(GLMappingLearned).where(GLMappingLearned.seller_phrase == seller_phrase)
    if source_seller is not None:
        stmt = stmt.where(GLMappingLearned.source_seller == source_seller)
    return (await session.execute(stmt)).scalars().first()


async def upsert_learned(
    session: AsyncSession,
    *,
    seller_phrase: str,
    source_seller: str | None,
    account_code: str,
    confirmed_by: str | None,
) -> GLMappingLearned:
    existing = await find_learned(session, seller_phrase=seller_phrase, source_seller=source_seller)
    if existing is not None:
        existing.account_code = account_code
        existing.confirmed_by = confirmed_by
        existing.confirmed_at = datetime.now(UTC)
        existing.hit_count = (existing.hit_count or 0) + 1
        await session.flush()
        return existing
    learned = GLMappingLearned(
        mapping_id=_new_id("gm"),
        seller_phrase=seller_phrase,
        source_seller=source_seller,
        account_code=account_code,
        confirmed_by=confirmed_by,
        confirmed_at=datetime.now(UTC),
        hit_count=1,
    )
    session.add(learned)
    await session.flush()
    return learned


async def get_line(session: AsyncSession, line_id: str) -> FinancialLine | None:
    return await session.get(FinancialLine, line_id)


async def split_parent_ids(session: AsyncSession, acquisition_id: str) -> set[str]:
    """Line ids that have split children (the non-counted container rows) for an acquisition."""
    stmt = select(FinancialLine.split_parent_id).where(
        FinancialLine.acquisition_id == acquisition_id,
        FinancialLine.split_parent_id.isnot(None),
    )
    return {pid for pid in (await session.execute(stmt)).scalars().all() if pid}


async def list_lines(session: AsyncSession, acquisition_id: str) -> Sequence[FinancialLine]:
    """Lines for the acquisition's *active* financial version only (older uploads stay queryable but
    don't bleed into the mapping view)."""
    period_id = await current_period_id(session, acquisition_id)
    if period_id is None:
        return []
    stmt = (
        select(FinancialLine)
        .where(FinancialLine.acquisition_id == acquisition_id, FinancialLine.period_id == period_id)
        .order_by(FinancialLine.line_id)
    )
    return (await session.execute(stmt)).scalars().all()

"""Year-one budget service (design doc §5.5): assemble the prior-year-vs-year-one budget, seed it
from the mapped actuals, and persist single-cell edits. Prior year is computed on read; only the
editable year-one cells are stored. Shared inputs (price/debt/equity) are NOT duplicated here —
the budget rolls UP into the canonical store (Part 6)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..mapping import repository as mapping_repo
from ..models.budget import Budget, BudgetLine
from ..models.enums import BudgetSource
from ..schemas.budget import BudgetCellUpdate, BudgetDoc, BudgetRow, BudgetTotals
from .budget import bucket_line_months, variance

_ZERO = Decimal(0)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def _prior_by_account(
    session: AsyncSession, acquisition_id: str
) -> dict[str, dict[int, Decimal]]:
    """Prior-year monthly actuals per GL, computed from the mapped lines' raw_payload (merged)."""
    lines = await mapping_repo.list_lines(session, acquisition_id)
    out: dict[str, dict[int, Decimal]] = {}
    for line in lines:
        if line.account_code is None or not line.raw_payload:
            continue
        bucket = out.setdefault(line.account_code, {})
        for idx, amount in bucket_line_months(line.raw_payload).items():
            bucket[idx] = bucket.get(idx, _ZERO) + amount
    return out


async def _lines(session: AsyncSession, acquisition_id: str) -> list[BudgetLine]:
    stmt = select(BudgetLine).where(BudgetLine.acquisition_id == acquisition_id)
    return list((await session.execute(stmt)).scalars().all())


async def _header(session: AsyncSession, acquisition_id: str) -> Budget | None:
    stmt = select(Budget).where(Budget.acquisition_id == acquisition_id)
    return (await session.execute(stmt)).scalars().first()


def _totals(rows: list[BudgetRow], section_by_code: dict[str, str | None]) -> BudgetTotals:
    def above_income(r: BudgetRow) -> bool:
        return section_by_code.get(r.account_code) == "Income"

    def above_expense(r: BudgetRow) -> bool:
        return section_by_code.get(r.account_code) == "Expense"

    p_rev = sum((r.prior_annual for r in rows if above_income(r)), _ZERO)
    y_rev = sum((r.year1_annual for r in rows if above_income(r)), _ZERO)
    p_op = sum((r.prior_annual for r in rows if above_expense(r)), _ZERO)
    y_op = sum((r.year1_annual for r in rows if above_expense(r)), _ZERO)
    return BudgetTotals(
        prior_revenue=p_rev,
        year1_revenue=y_rev,
        prior_opex=p_op,
        year1_opex=y_op,
        prior_noi=p_rev - p_op,
        year1_noi=y_rev - y_op,
    )


async def get_budget(session: AsyncSession, acquisition_id: str) -> BudgetDoc:
    header = await _header(session, acquisition_id)
    lines = await _lines(session, acquisition_id)
    prior = await _prior_by_account(session, acquisition_id)
    accounts = {a.account_code: a for a in await mapping_repo.list_accounts(session)}

    year1: dict[str, dict[int, Decimal]] = {}
    sources: dict[str, set[str]] = {}
    overridden: dict[str, bool] = {}
    notes: dict[str, str | None] = {}
    for bl in lines:
        if bl.year1_amount is not None:
            year1.setdefault(bl.account_code, {})[bl.month_index] = bl.year1_amount
        sources.setdefault(bl.account_code, set()).add(bl.source)
        overridden[bl.account_code] = overridden.get(bl.account_code, False) or bl.is_overridden
        if bl.note:
            notes[bl.account_code] = bl.note

    def sort_key(code: str) -> tuple[int, str]:
        acct = accounts.get(code)
        return (acct.sort if acct and acct.sort is not None else 9999, code)

    rows: list[BudgetRow] = []
    for code in sorted(set(year1) | set(prior), key=sort_key):
        acct = accounts.get(code)
        p_months = prior.get(code, {})
        y_months = year1.get(code, {})
        p_annual = sum(p_months.values(), _ZERO)
        y_annual = sum(y_months.values(), _ZERO)
        v_abs, v_pct = variance(p_annual, y_annual)
        src = sources.get(code, set())
        source = (
            next(iter(src)) if len(src) == 1 else ("mixed" if src else BudgetSource.ACTUALS.value)
        )
        rows.append(
            BudgetRow(
                account_code=code,
                name=acct.name if acct else code,
                section=acct.section if acct else None,
                source=source,
                prior_months=[p_months.get(i) for i in range(1, 13)],
                year1_months=[y_months.get(i) for i in range(1, 13)],
                prior_annual=p_annual,
                year1_annual=y_annual,
                var_abs=v_abs,
                var_pct=v_pct,
                is_overridden=overridden.get(code, False),
                note=notes.get(code),
            )
        )
    totals = _totals(rows, {c: (a.section if a else None) for c, a in accounts.items()})
    status = header.status if header else "draft"
    return BudgetDoc(status=status, rows=rows, totals=totals)


async def seed_budget(session: AsyncSession, acquisition_id: str) -> BudgetDoc:
    """Prefill year-one from the prior-year mapped actuals (source=actuals), idempotently — never
    clobbering a cell a human has overridden. (Defaults + placeholders arrive with the defaults
    engine.)"""
    header = await _header(session, acquisition_id)
    if header is None:
        period_id = await mapping_repo.current_period_id(session, acquisition_id)
        header = Budget(
            budget_id=_new_id("bud"), acquisition_id=acquisition_id, source_period_id=period_id
        )
        session.add(header)

    existing = {(bl.account_code, bl.month_index) for bl in await _lines(session, acquisition_id)}
    prior = await _prior_by_account(session, acquisition_id)
    for code, months in prior.items():
        for idx, amount in months.items():
            if (code, idx) in existing:
                continue  # don't overwrite (especially human overrides)
            session.add(
                BudgetLine(
                    budget_line_id=_new_id("bl"),
                    acquisition_id=acquisition_id,
                    account_code=code,
                    month_index=idx,
                    year1_amount=amount,
                    source=BudgetSource.ACTUALS.value,
                )
            )
    await session.commit()
    return await get_budget(session, acquisition_id)


async def patch_cell(
    session: AsyncSession, acquisition_id: str, body: BudgetCellUpdate, *, actor: str | None
) -> BudgetDoc:
    """Edit one year-one cell → flips it to a human override (provenance retained)."""
    stmt = select(BudgetLine).where(
        BudgetLine.acquisition_id == acquisition_id,
        BudgetLine.account_code == body.account_code,
        BudgetLine.month_index == body.month_index,
    )
    line = (await session.execute(stmt)).scalars().first()
    now = datetime.now(UTC)
    if line is None:
        line = BudgetLine(
            budget_line_id=_new_id("bl"),
            acquisition_id=acquisition_id,
            account_code=body.account_code,
            month_index=body.month_index,
            source=BudgetSource.PLACEHOLDER.value,
        )
        session.add(line)
    line.year1_amount = body.year1_amount
    line.is_overridden = True
    line.overridden_by = actor
    line.overridden_at = now
    if body.note is not None:
        line.note = body.note
    await session.commit()
    return await get_budget(session, acquisition_id)

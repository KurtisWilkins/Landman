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

from ..core.config import settings
from ..mapping import repository as mapping_repo
from ..models.acquisitions import Acquisition
from ..models.budget import Budget, BudgetLine
from ..models.enums import BudgetSource, BudgetStatus
from ..schemas.budget import BudgetCellUpdate, BudgetDoc, BudgetRow, BudgetTotals
from .budget import bucket_line_months, variance
from .budget_defaults import DefaultsContext, all_defaults
from .engine import NoiLine, normalized_noi

_ZERO = Decimal(0)


class BudgetError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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
            notes.setdefault(bl.account_code, bl.note)  # one note per account; keep first seen

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
    status = header.status if header else BudgetStatus.DRAFT.value
    placeholders, unmapped = await readiness(session, acquisition_id)
    return BudgetDoc(
        status=status,
        rows=rows,
        totals=totals,
        placeholder_count=placeholders,
        unmapped_count=unmapped,
    )


async def _defaults_context(session: AsyncSession, acquisition_id: str) -> DefaultsContext:
    acq = await session.get(Acquisition, acquisition_id)
    return DefaultsContext(
        site_count=acq.site_count if acq else None,
        shield_monthly=settings.shield_monthly,
        shield_account_code=settings.shield_account_code,
        mktg_website_monthly=settings.mktg_website_monthly,
        mktg_website_account_code=settings.mktg_website_account_code,
        mktg_secondary_monthly=settings.mktg_secondary_monthly,
        mktg_secondary_account_code=settings.mktg_secondary_account_code,
        ppc_rate=settings.ppc_rate,
        ppc_target_volume=settings.ppc_target_volume,
        ppc_intercompany_pct=settings.ppc_intercompany_pct,
        ppc_google_account_code=settings.ppc_google_account_code,
        ppc_intercompany_account_code=settings.ppc_intercompany_account_code,
    )


async def seed_budget(session: AsyncSession, acquisition_id: str) -> BudgetDoc:
    """Prefill year-one, idempotently and without clobbering human overrides: (1) prior-year mapped
    actuals (source=actuals); (2) the defaults engine for GLs the actuals lack (source=default) —
    Shield supersedes any historical line. Unconfigured default rules produce nothing, so this is
    actuals-only until the GL account codes + PPC params are set."""
    header = await _header(session, acquisition_id)
    if header is None:
        period_id = await mapping_repo.current_period_id(session, acquisition_id)
        header = Budget(
            budget_id=_new_id("bud"), acquisition_id=acquisition_id, source_period_id=period_id
        )
        session.add(header)

    cells = {(bl.account_code, bl.month_index): bl for bl in await _lines(session, acquisition_id)}

    # 1) Prior-year actuals.
    prior = await _prior_by_account(session, acquisition_id)
    for code, months in prior.items():
        for idx, amount in months.items():
            if (code, idx) in cells:
                continue
            line = BudgetLine(
                budget_line_id=_new_id("bl"),
                acquisition_id=acquisition_id,
                account_code=code,
                month_index=idx,
                year1_amount=amount,
                source=BudgetSource.ACTUALS.value,
            )
            session.add(line)
            cells[(code, idx)] = line

    # 2) Defaults (our numbers). No-op until the rates/codes are configured; only post to GL
    #    accounts that actually exist in the chart.
    ctx = await _defaults_context(session, acquisition_id)
    known_codes = {a.account_code for a in await mapping_repo.list_accounts(session)}
    for dl in all_defaults(ctx):
        if dl.account_code not in known_codes:
            continue
        for idx in range(1, 13):
            existing_cell = cells.get((dl.account_code, idx))
            if existing_cell is not None:
                # Shield overrides history; never touch a human override or a gap-fill that exists.
                if dl.overrides_actuals and not existing_cell.is_overridden:
                    existing_cell.year1_amount = dl.monthly_amount
                    existing_cell.source = BudgetSource.DEFAULT.value
                    existing_cell.default_rule_key = dl.default_rule_key
                continue
            line = BudgetLine(
                budget_line_id=_new_id("bl"),
                acquisition_id=acquisition_id,
                account_code=dl.account_code,
                month_index=idx,
                year1_amount=dl.monthly_amount,
                source=BudgetSource.DEFAULT.value,
                default_rule_key=dl.default_rule_key,
            )
            session.add(line)
            cells[(dl.account_code, idx)] = line

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
        # A new cell must target a real GL account (FK), else commit would 500. Reject early.
        known_codes = {a.account_code for a in await mapping_repo.list_accounts(session)}
        if body.account_code not in known_codes:
            raise BudgetError("invalid_account", f"Unknown GL account {body.account_code}.")
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
    header = await _header(session, acquisition_id)
    if header is not None and header.status == BudgetStatus.LOCKED.value:
        header.status = BudgetStatus.DRAFT.value  # editing a locked budget forces a re-lock
        header.locked_by = None
        header.locked_at = None
    await session.commit()
    return await get_budget(session, acquisition_id)


async def readiness(session: AsyncSession, acquisition_id: str) -> tuple[int, int]:
    """(unresolved placeholders, unmapped financial lines). Both must be 0 to lock."""
    placeholders = sum(
        1
        for bl in await _lines(session, acquisition_id)
        if bl.source == BudgetSource.PLACEHOLDER.value and not bl.is_overridden
    )
    # Split parents are non-counted containers (account_code NULL by design) — exclude them, or a
    # split would block the lock forever. build_review() excludes them the same way.
    split_parents = await mapping_repo.split_parent_ids(session, acquisition_id)
    unmapped = sum(
        1
        for line in await mapping_repo.list_lines(session, acquisition_id)
        if line.account_code is None and line.line_id not in split_parents
    )
    return placeholders, unmapped


async def locked_stabilized(
    session: AsyncSession, acquisition_id: str
) -> tuple[Decimal, Decimal] | None:
    """Stabilized (revenue, opex) rolled up from a LOCKED budget via the SAME normalized_noi
    machinery the NOI bridge uses (so the two stabilized paths reconcile). None unless locked."""
    header = await _header(session, acquisition_id)
    if header is None or header.status != BudgetStatus.LOCKED.value:
        return None
    lines = await _lines(session, acquisition_id)
    if not lines:
        return None
    accounts = {a.account_code: a for a in await mapping_repo.list_accounts(session)}
    noi_lines: list[NoiLine] = []
    for bl in lines:
        if bl.year1_amount is None:
            continue
        acct = accounts.get(bl.account_code)
        placement = bl.noi_placement or (acct.default_noi_placement if acct else None) or "above"
        noi_lines.append(
            NoiLine(
                amount=bl.year1_amount,
                noi_placement=placement,
                is_expense=bool(acct and acct.section == "Expense"),
                is_addback=False,
            )
        )
    bridge = normalized_noi(noi_lines)
    return bridge.gross_revenue, bridge.operating_expense


async def lock(session: AsyncSession, acquisition_id: str, *, by: str | None) -> None:
    """Lock the budget (gated on zero placeholders + zero unmapped). The caller then recomputes."""
    header = await _header(session, acquisition_id)
    if header is None:
        raise BudgetError("not_seeded", "Seed the budget before locking.")
    placeholders, unmapped = await readiness(session, acquisition_id)
    if placeholders or unmapped:
        raise BudgetError(
            "not_ready",
            f"{placeholders} placeholder(s) and {unmapped} unmapped line(s) must be cleared.",
        )
    header.status = BudgetStatus.LOCKED.value
    header.locked_by = by
    header.locked_at = datetime.now(UTC)
    await session.commit()


async def unlock(session: AsyncSession, acquisition_id: str) -> None:
    header = await _header(session, acquisition_id)
    if header is not None:
        header.status = BudgetStatus.DRAFT.value
        header.locked_by = None
        header.locked_at = None
        await session.commit()

"""Year-one underwriting budget service (design doc §5.5): assemble the two-column prior-year /
year-one grid, seed it from the mapped actuals, and persist edits.

The grid is annual — one row per line, where a line is either a canonical GL account or a custom
(non-GL) line item. BOTH columns are editable: prior-year defaults to the mapped actuals but can be
overridden (``prior_amount``) to correct an upload; year-one defaults to prior. A line removed from
the year-one projection keeps its prior as reference. The only outputs that matter — TOTAL REVENUE,
TOTAL EXPENSES, NOI — are computed by the pure ``roll_up``. Shared inputs (price/debt/equity) are
NOT duplicated here; the budget rolls UP into the canonical store's stabilized NOI.
"""

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
from ..models.reference import GLAccount
from ..schemas.budget import (
    BudgetDoc,
    BudgetLineCreate,
    BudgetLinePatch,
    BudgetRow,
    BudgetTotals,
)
from .budget import GridLine, GridTotals, bucket_line_months, roll_up, variance
from .budget_defaults import DefaultsContext, all_defaults

_ZERO = Decimal(0)
_MONTHS_PER_YEAR = Decimal(12)


class BudgetError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def _prior_actuals(session: AsyncSession, acquisition_id: str) -> dict[str, Decimal]:
    """Annual prior-year actual per GL account, computed from the mapped lines' raw_payload."""
    lines = await mapping_repo.list_lines(session, acquisition_id)
    out: dict[str, Decimal] = {}
    for line in lines:
        if line.account_code is None or not line.raw_payload:
            continue
        total = sum(bucket_line_months(line.raw_payload).values(), _ZERO)
        out[line.account_code] = out.get(line.account_code, _ZERO) + total
    return out


async def _lines(session: AsyncSession, acquisition_id: str) -> list[BudgetLine]:
    stmt = select(BudgetLine).where(BudgetLine.acquisition_id == acquisition_id)
    return list((await session.execute(stmt)).scalars().all())


async def _header(session: AsyncSession, acquisition_id: str) -> Budget | None:
    stmt = select(Budget).where(Budget.acquisition_id == acquisition_id)
    return (await session.execute(stmt)).scalars().first()


async def _accounts(session: AsyncSession) -> dict[str, GLAccount]:
    return {a.account_code: a for a in await mapping_repo.list_accounts(session)}


def _placement(bl: BudgetLine, acct: GLAccount | None) -> str:
    return bl.noi_placement or (acct.default_noi_placement if acct else None) or "above"


def _totals(gt: GridTotals) -> BudgetTotals:
    # Map the pure GridTotals to the (revenue/opex/noi) shape the API exposes.
    return BudgetTotals(
        prior_revenue=gt.prior_revenue,
        year1_revenue=gt.year1_revenue,
        prior_opex=gt.prior_expense,
        year1_opex=gt.year1_expense,
        prior_noi=gt.prior_noi,
        year1_noi=gt.year1_noi,
    )


async def get_budget(session: AsyncSession, acquisition_id: str) -> BudgetDoc:
    header = await _header(session, acquisition_id)
    lines = await _lines(session, acquisition_id)
    prior = await _prior_actuals(session, acquisition_id)
    accounts = await _accounts(session)

    def sort_key(bl: BudgetLine) -> tuple[int, int, str]:
        acct = accounts.get(bl.account_code) if bl.account_code else None
        return (
            0 if acct else 1,
            acct.sort if acct and acct.sort is not None else 9999,
            bl.account_code or bl.custom_label or "",
        )

    rows: list[BudgetRow] = []
    grid: list[GridLine] = []
    seen: set[str] = set()

    for bl in sorted(lines, key=sort_key):
        acct = accounts.get(bl.account_code) if bl.account_code else None
        if bl.account_code is not None:
            seen.add(bl.account_code)
        prior_actual = prior.get(bl.account_code, _ZERO) if bl.account_code else _ZERO
        prior_val = bl.prior_amount if bl.prior_amount is not None else prior_actual
        year1_val = bl.year1_amount if bl.year1_amount is not None else prior_val
        section = bl.section or (acct.section if acct else None)
        placement = _placement(bl, acct)
        name = (acct.name if acct else None) or bl.custom_label or (bl.account_code or "—")
        source = "edited" if bl.is_overridden else bl.source
        v_abs, v_pct = variance(prior_val, _ZERO if bl.removed else year1_val)
        rows.append(
            BudgetRow(
                line_id=bl.budget_line_id,
                account_code=bl.account_code,
                custom_label=bl.custom_label,
                name=name,
                section=section,
                source=source,
                prior_annual=prior_val,
                year1_annual=year1_val,
                var_abs=v_abs,
                var_pct=v_pct,
                is_overridden=bl.is_overridden,
                prior_overridden=bl.prior_amount is not None,
                removed=bl.removed,
                flagged_for_promotion=bl.flagged_for_promotion,
                note=bl.note,
            )
        )
        grid.append(
            GridLine(
                placement=placement,
                is_expense=section == "Expense",
                prior=prior_val,
                year1=_ZERO if bl.removed else year1_val,
            )
        )

    # Prior-actuals accounts not yet seeded: show prior (read-only ref) with year-one defaulting
    # to prior, so the grid isn't empty before "Seed". Editing one creates a stored line.
    for code, prior_val in prior.items():
        if code in seen:
            continue
        acct = accounts.get(code)
        section = acct.section if acct else None
        v_abs, v_pct = variance(prior_val, prior_val)
        rows.append(
            BudgetRow(
                line_id=None,
                account_code=code,
                custom_label=None,
                name=acct.name if acct else code,
                section=section,
                source=BudgetSource.ACTUALS.value,
                prior_annual=prior_val,
                year1_annual=prior_val,
                var_abs=v_abs,
                var_pct=v_pct,
                is_overridden=False,
                prior_overridden=False,
                removed=False,
                flagged_for_promotion=False,
                note=None,
            )
        )
        grid.append(
            GridLine(
                placement=(acct.default_noi_placement if acct else None) or "above",
                is_expense=section == "Expense",
                prior=prior_val,
                year1=prior_val,
            )
        )

    placeholders, unmapped = await readiness(session, acquisition_id)
    return BudgetDoc(
        status=header.status if header else BudgetStatus.DRAFT.value,
        rows=rows,
        totals=_totals(roll_up(grid)),
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


async def _ensure_header(session: AsyncSession, acquisition_id: str) -> Budget:
    header = await _header(session, acquisition_id)
    if header is None:
        period_id = await mapping_repo.current_period_id(session, acquisition_id)
        header = Budget(
            budget_id=_new_id("bud"), acquisition_id=acquisition_id, source_period_id=period_id
        )
        session.add(header)
    return header


def _invalidate_lock(header: Budget | None) -> None:
    if header is not None and header.status == BudgetStatus.LOCKED.value:
        header.status = BudgetStatus.DRAFT.value  # editing a locked budget forces a re-lock
        header.locked_by = None
        header.locked_at = None


async def seed_budget(session: AsyncSession, acquisition_id: str) -> BudgetDoc:
    """Prefill annual rows idempotently: (1) one row per mapped-actuals GL (year-one defaults to
    the prior actual); (2) the defaults engine for GLs the actuals lack (annual = monthly × 12;
    Shield supersedes history). Never clobbers a human override."""
    await _ensure_header(session, acquisition_id)
    by_account = {
        bl.account_code: bl for bl in await _lines(session, acquisition_id) if bl.account_code
    }
    accounts = await _accounts(session)

    for code, prior_val in (await _prior_actuals(session, acquisition_id)).items():
        if code in by_account:
            continue
        acct = accounts.get(code)
        line = BudgetLine(
            budget_line_id=_new_id("bl"),
            acquisition_id=acquisition_id,
            account_code=code,
            month_index=0,
            year1_amount=prior_val,
            section=acct.section if acct else None,
            source=BudgetSource.ACTUALS.value,
        )
        session.add(line)
        by_account[code] = line

    ctx = await _defaults_context(session, acquisition_id)
    for dl in all_defaults(ctx):
        if dl.account_code not in accounts:  # only post to GLs that exist in the chart (FK-safe)
            continue
        annual = dl.monthly_amount * _MONTHS_PER_YEAR
        acct = accounts.get(dl.account_code)
        existing = by_account.get(dl.account_code)
        if existing is not None:
            if dl.overrides_actuals and not existing.is_overridden:
                existing.year1_amount = annual
                existing.source = BudgetSource.DEFAULT.value
                existing.default_rule_key = dl.default_rule_key
            continue
        line = BudgetLine(
            budget_line_id=_new_id("bl"),
            acquisition_id=acquisition_id,
            account_code=dl.account_code,
            month_index=0,
            year1_amount=annual,
            section=acct.section if acct else None,
            source=BudgetSource.DEFAULT.value,
            default_rule_key=dl.default_rule_key,
        )
        session.add(line)
        by_account[dl.account_code] = line

    await session.commit()
    return await get_budget(session, acquisition_id)


async def _resolve_line(
    session: AsyncSession, acquisition_id: str, *, line_id: str | None, account_code: str | None
) -> BudgetLine | None:
    if line_id is not None:
        line = await session.get(BudgetLine, line_id)
        return line if line and line.acquisition_id == acquisition_id else None
    if account_code is not None:
        stmt = select(BudgetLine).where(
            BudgetLine.acquisition_id == acquisition_id,
            BudgetLine.account_code == account_code,
        )
        return (await session.execute(stmt)).scalars().first()
    return None


async def patch_line(
    session: AsyncSession, acquisition_id: str, body: BudgetLinePatch, *, actor: str | None
) -> BudgetDoc:
    """Edit a line's prior and/or year-one amount. Editing year-one flips it to a human override;
    editing prior records a prior override (provenance kept — the uploaded value is still derivable
    from the mapped actuals). A not-yet-seeded GL row is created on first edit."""
    line = await _resolve_line(
        session, acquisition_id, line_id=body.line_id, account_code=body.account_code
    )
    now = datetime.now(UTC)
    if line is None:
        if body.account_code is None:
            raise BudgetError("line_not_found", "No such budget line.")
        accounts = await _accounts(session)
        if body.account_code not in accounts:
            raise BudgetError("invalid_account", f"Unknown GL account {body.account_code}.")
        acct = accounts[body.account_code]
        line = BudgetLine(
            budget_line_id=_new_id("bl"),
            acquisition_id=acquisition_id,
            account_code=body.account_code,
            month_index=0,
            section=acct.section,
            source=BudgetSource.ACTUALS.value,
        )
        session.add(line)
    if body.year1_amount is not None:
        line.year1_amount = body.year1_amount
        line.removed = False
        line.is_overridden = True
        line.overridden_by = actor
        line.overridden_at = now
    if body.prior_amount is not None:
        line.prior_amount = body.prior_amount
    if body.note is not None:
        line.note = body.note
    _invalidate_lock(await _header(session, acquisition_id))
    await session.commit()
    return await get_budget(session, acquisition_id)


async def add_line(
    session: AsyncSession, acquisition_id: str, body: BudgetLineCreate, *, actor: str | None
) -> BudgetDoc:
    """Add a row: a canonical GL (pick from the chart) or a custom line (free-text label, flagged
    to promote to the GL chart later)."""
    await _ensure_header(session, acquisition_id)
    if body.account_code is not None:
        accounts = await _accounts(session)
        if body.account_code not in accounts:
            raise BudgetError("invalid_account", f"Unknown GL account {body.account_code}.")
        if await _resolve_line(
            session, acquisition_id, line_id=None, account_code=body.account_code
        ):
            raise BudgetError("duplicate_line", "That GL is already on the budget.")
        acct = accounts[body.account_code]
        line = BudgetLine(
            budget_line_id=_new_id("bl"),
            acquisition_id=acquisition_id,
            account_code=body.account_code,
            month_index=0,
            section=body.section or acct.section,
            prior_amount=body.prior_amount,
            year1_amount=body.year1_amount,
            source=BudgetSource.PLACEHOLDER.value,
            is_overridden=body.year1_amount is not None,
            overridden_by=actor if body.year1_amount is not None else None,
        )
    else:
        if not body.custom_label or not body.section:
            raise BudgetError("missing_fields", "A custom line needs a label and a section.")
        line = BudgetLine(
            budget_line_id=_new_id("bl"),
            acquisition_id=acquisition_id,
            account_code=None,
            custom_label=body.custom_label,
            month_index=0,
            section=body.section,
            prior_amount=body.prior_amount,
            year1_amount=body.year1_amount,
            source=BudgetSource.CUSTOM.value,
            flagged_for_promotion=True,  # not in the GL chart → flag for promotion
            is_overridden=body.year1_amount is not None,
            overridden_by=actor if body.year1_amount is not None else None,
        )
    session.add(line)
    _invalidate_lock(await _header(session, acquisition_id))
    await session.commit()
    return await get_budget(session, acquisition_id)


async def remove_line(
    session: AsyncSession, acquisition_id: str, line_id: str, *, actor: str | None
) -> BudgetDoc:
    """Remove a row. A custom line is deleted outright; a GL/actuals line is dropped from the
    year-one projection (``removed``) but keeps its prior value as reference (Q3)."""
    line = await session.get(BudgetLine, line_id)
    if line is None or line.acquisition_id != acquisition_id:
        raise BudgetError("line_not_found", "No such budget line.")
    if line.account_code is None:
        await session.delete(line)
    else:
        line.removed = True
        line.is_overridden = True
        line.overridden_by = actor
        line.overridden_at = datetime.now(UTC)
    _invalidate_lock(await _header(session, acquisition_id))
    await session.commit()
    return await get_budget(session, acquisition_id)


async def readiness(session: AsyncSession, acquisition_id: str) -> tuple[int, int]:
    """(unresolved placeholders, unmapped financial lines). Both must be 0 to lock."""
    placeholders = sum(
        1
        for bl in await _lines(session, acquisition_id)
        if bl.source == BudgetSource.PLACEHOLDER.value and not bl.is_overridden and not bl.removed
    )
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
    """Stabilized (revenue, opex) rolled up from a LOCKED budget via the SAME pure ``roll_up`` the
    grid uses, so the grid's year-one NOI and the downstream stabilized NOI reconcile. None unless
    locked."""
    header = await _header(session, acquisition_id)
    if header is None or header.status != BudgetStatus.LOCKED.value:
        return None
    lines = await _lines(session, acquisition_id)
    if not lines:
        return None
    accounts = await _accounts(session)
    grid: list[GridLine] = []
    for bl in lines:
        if bl.removed:
            continue
        acct = accounts.get(bl.account_code) if bl.account_code else None
        section = bl.section or (acct.section if acct else None)
        year1 = bl.year1_amount if bl.year1_amount is not None else (bl.prior_amount or _ZERO)
        grid.append(
            GridLine(
                placement=_placement(bl, acct),
                is_expense=section == "Expense",
                prior=_ZERO,
                year1=year1,
            )
        )
    totals = roll_up(grid)
    return totals.year1_revenue, totals.year1_expense


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

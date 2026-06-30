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
from ..models.budget import Budget, BudgetLine
from ..models.enums import BudgetSource, BudgetStatus
from ..models.labor import LaborPosition
from ..models.operating import SOURCE_MANUAL, OperationalInputs, UnitGroup
from ..models.reference import GLAccount
from ..schemas.budget import (
    BudgetDoc,
    BudgetGroup,
    BudgetLineCreate,
    BudgetLinePatch,
    BudgetLineRef,
    BudgetRow,
    BudgetTotals,
)
from .budget import (
    GridLine,
    GridTotals,
    TreeNode,
    bucket_line_months,
    roll_up,
    roll_up_tree,
    variance,
)
from .defaults_config import effective_rules
from .defaults_rules import DefaultComputation, DriverContext, compute_default
from .labor import total_headcount
from .operating import UnitGroupInput, billable_unit_total, units_need_input

_ZERO = Decimal(0)


class BudgetError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def _prior_actuals(session: AsyncSession, acquisition_id: str) -> dict[str, Decimal]:
    """Annual prior-year actual per GL account from the mapped lines.

    A recap P&L carries per-month columns in ``raw_payload`` → sum the calendar-month buckets. An
    annual-only source (the offering memorandum, or a generic non-recap P&L) has no month columns →
    use the line's annual ``amount``. This is what lets OM-seeded financials populate prior-year,
    not just an uploaded recap."""
    lines = await mapping_repo.list_lines(session, acquisition_id)
    out: dict[str, Decimal] = {}
    for line in lines:
        if line.account_code is None:
            continue
        months = bucket_line_months(line.raw_payload) if line.raw_payload else {}
        total = sum(months.values(), _ZERO) if months else (line.amount or _ZERO)
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

    def sort_key(bl: BudgetLine) -> tuple[int, int, int, str]:
        acct = accounts.get(bl.account_code) if bl.account_code else None
        # A manual drag-order (sort_order) wins; rows never moved fall back to the GL chart order.
        # Within the frontend's section grouping this gives each section its own custom order.
        return (
            bl.sort_order if bl.sort_order is not None else 1_000_000,
            0 if acct else 1,
            acct.sort if acct and acct.sort is not None else 9999,
            bl.account_code or bl.custom_label or "",
        )

    rows: list[BudgetRow] = []
    grid: list[GridLine] = []
    seen: set[str] = set()
    # Leaf amounts (code → prior, year1) for the hierarchical roll-up that produces group subtotals.
    amounts: dict[str, tuple[Decimal, Decimal]] = {}

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
        # A custom line keeps its "custom" provenance even when edited; otherwise an edit shows
        # "edited" over the stored source.
        if bl.source == BudgetSource.CUSTOM.value:
            source = BudgetSource.CUSTOM.value
        elif bl.is_overridden:
            source = "edited"
        else:
            source = bl.source
        year1_eff = _ZERO if bl.removed else year1_val
        v_abs, v_pct = variance(prior_val, year1_eff)
        rows.append(
            BudgetRow(
                line_id=bl.budget_line_id,
                account_code=bl.account_code,
                custom_label=bl.custom_label,
                name=name,
                section=section,
                parent_code=acct.parent_code if acct else None,
                is_contra=acct.is_contra if acct else False,
                tier=acct.tier if acct else None,
                source=source,
                prior_annual=prior_val,
                year1_annual=year1_val,
                var_abs=v_abs,
                var_pct=v_pct,
                is_overridden=bl.is_overridden,
                prior_overridden=bl.prior_amount is not None,
                removed=bl.removed,
                flagged_for_promotion=bl.flagged_for_promotion,
                revertible=bl.default_rule_key is not None and bl.is_overridden,
                note=bl.note,
            )
        )
        if bl.account_code is not None:
            amounts[bl.account_code] = (prior_val, year1_eff)
        grid.append(
            GridLine(
                placement=placement,
                is_expense=section == "Expense",
                prior=prior_val,
                year1=year1_eff,
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
                parent_code=acct.parent_code if acct else None,
                is_contra=acct.is_contra if acct else False,
                tier=acct.tier if acct else None,
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
        amounts[code] = (prior_val, prior_val)
        grid.append(
            GridLine(
                placement=(acct.default_noi_placement if acct else None) or "above",
                is_expense=section == "Expense",
                prior=prior_val,
                year1=prior_val,
            )
        )

    groups = _build_groups(accounts, amounts)
    placeholders, unmapped = await readiness(session, acquisition_id)
    return BudgetDoc(
        status=header.status if header else BudgetStatus.DRAFT.value,
        rows=rows,
        groups=groups,
        totals=_totals(roll_up(grid)),
        placeholder_count=placeholders,
        unmapped_count=unmapped,
    )


def _build_groups(
    accounts: dict[str, GLAccount], amounts: dict[str, tuple[Decimal, Decimal]]
) -> list[BudgetGroup]:
    """Subtotal every chart group/sub-group that has at least one budget row beneath it, via the
    pure ``roll_up_tree``. Mirrors the source's "Total - …" rows; the UI renders these numbers
    directly (no client-side math)."""
    nodes = [
        TreeNode(
            code=a.account_code,
            parent_code=a.parent_code,
            section=a.section,
            placement=a.default_noi_placement or "above",
        )
        for a in accounts.values()
    ]
    rollup = roll_up_tree(nodes, amounts)
    # Only emit headers for ancestor groups of the present leaves (skip empty branches + the leaves
    # themselves), in chart order.
    present_groups: set[str] = set()
    for code in amounts:
        cur = accounts.get(code)
        cur = accounts.get(cur.parent_code) if cur and cur.parent_code else None
        while cur is not None:
            present_groups.add(cur.account_code)
            cur = accounts.get(cur.parent_code) if cur.parent_code else None
    out: list[BudgetGroup] = []
    for a in sorted(accounts.values(), key=lambda x: x.sort if x.sort is not None else 1_000_000):
        if a.account_code not in present_groups:
            continue
        prior_val, year1_val = rollup.subtotals.get(a.account_code, (_ZERO, _ZERO))
        out.append(
            BudgetGroup(
                code=a.account_code,
                name=a.name,
                level=a.level.value if hasattr(a.level, "value") else str(a.level),
                section=a.section,
                parent_code=a.parent_code,
                prior_annual=prior_val,
                year1_annual=year1_val,
                var_abs=year1_val - prior_val,
            )
        )
    return out


def _subtree_codes(target: str, accounts: dict[str, GLAccount]) -> set[str]:
    """``target`` plus all GL accounts beneath it (so a coarse default to a parent can tell whether
    the seller already mapped detail into the bucket)."""
    children: dict[str, list[str]] = {}
    for code, acct in accounts.items():
        if acct.parent_code:
            children.setdefault(acct.parent_code, []).append(code)
    out = {target}
    stack = [target]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def _subtree_has_actuals(
    target: str, by_account: dict[str, BudgetLine], accounts: dict[str, GLAccount]
) -> bool:
    """True if the seller already has a (non-default) line anywhere in ``target``'s subtree, so a
    gap-fill default skips it rather than double-counting (605400 utilities vs its 605410 child)."""
    for code in _subtree_codes(target, accounts):
        bl = by_account.get(code)
        if bl is not None and not bl.removed and bl.source != BudgetSource.DEFAULT.value:
            return True
    return False


def _gross_revenue_base(
    by_account: dict[str, BudgetLine],
    accounts: dict[str, GLAccount],
    prior: dict[str, Decimal],
) -> Decimal | None:
    """Projected operating revenue, computed ONCE for the percent-of-gross rules. Excludes
    default-generated lines so adding a default never feeds back into the % base. None when zero
    (the dependent rule then reports needs-input rather than computing against $0)."""
    total = _ZERO
    seen: set[str] = set()
    for code, bl in by_account.items():
        acct = accounts.get(code)
        if acct is None or acct.section != "Income" or bl.removed:
            continue
        if bl.source == BudgetSource.DEFAULT.value:
            continue
        if bl.year1_amount is not None:
            val = bl.year1_amount
        elif bl.prior_amount is not None:
            val = bl.prior_amount
        else:
            val = prior.get(code, _ZERO)
        total += val
        seen.add(code)
    for code, val in prior.items():
        acct = accounts.get(code)
        if code not in seen and acct is not None and acct.section == "Income":
            total += val
    return total if total > _ZERO else None


async def roster_headcount(session: AsyncSession, acquisition_id: str) -> int | None:
    """The authoritative headcount = the Labor roster total (single source of truth). None when the
    roster is empty, so the payroll-budget default reports needs-input rather than guessing."""
    counts = list(
        (
            await session.execute(
                select(LaborPosition.headcount).where(
                    LaborPosition.acquisition_id == acquisition_id
                )
            )
        )
        .scalars()
        .all()
    )
    return total_headcount(counts) if counts else None


def _effective_electric(op: OperationalInputs | None, prior: dict[str, Decimal]) -> Decimal | None:
    """The Electric driver: a manual override wins; otherwise the Electric line that comes through
    the budget (the mapped prior-year actual on the configured Electric account, 605410); otherwise
    any seeded value (e.g. from the OM) so an unmapped electric line doesn't drop a captured number.
    """
    if op is not None and op.electric_source == SOURCE_MANUAL:
        return op.electric_annual
    code = settings.electric_account_code
    budget = prior.get(code) if code else None
    if budget is not None:
        return budget
    return op.electric_annual if op is not None else None


async def _driver_context(
    session: AsyncSession,
    acquisition_id: str,
    by_account: dict[str, BudgetLine],
    accounts: dict[str, GLAccount],
    prior: dict[str, Decimal],
) -> DriverContext:
    """Assemble the defaults drivers: the gross-revenue base + the operational inputs (electric,
    billable units, headcount) + the prior-year map (for the property-tax uplift)."""
    op = await session.get(OperationalInputs, acquisition_id)
    groups = (
        (await session.execute(select(UnitGroup).where(UnitGroup.acquisition_id == acquisition_id)))
        .scalars()
        .all()
    )
    inputs = [
        UnitGroupInput(category=g.category, count=g.count, billable=g.billable) for g in groups
    ]
    # Electric drives the utility bill-back default. A manual override wins; otherwise default to
    # the Electric line that comes through the budget (the mapped prior-year actual, 605410), so the
    # bill-back computes without the operator re-keying a number the budget already has.
    return DriverContext(
        gross_revenue=_gross_revenue_base(by_account, accounts, prior),
        electric_annual=_effective_electric(op, prior),
        billable_units=billable_unit_total(inputs),
        units_complete=not units_need_input(inputs),
        headcount=await roster_headcount(session, acquisition_id),  # Labor roster = SSOT
        prior_year=prior,
    )


async def _apply_defaults_lines(
    session: AsyncSession,
    acquisition_id: str,
    by_account: dict[str, BudgetLine],
    accounts: dict[str, GLAccount],
) -> None:
    """Compute each rule and post it onto its budget line (no commit). Never clobbers a manual
    override (manual sticks); gap-fill rules skip a bucket the seller already filled; a NeedsInput
    rule posts nothing (the panel surfaces the prompt); the bill-back lands as a negative contra."""
    prior = await _prior_actuals(session, acquisition_id)
    ctx = await _driver_context(session, acquisition_id, by_account, accounts, prior)
    for spec in await effective_rules(session):
        result = compute_default(spec, ctx)
        if not isinstance(result, DefaultComputation):
            continue  # disabled or needs-input → nothing to post
        target = result.target_account_code
        if target not in accounts:  # FK-safe: only post to chart accounts
            continue
        existing = by_account.get(target)
        if existing is not None and existing.is_overridden:
            continue  # a deliberate manual edit wins over the default
        if not spec.overrides_actuals and _subtree_has_actuals(target, by_account, accounts):
            continue  # gap-fill: the seller already has this bucket — don't double-count
        if existing is not None:
            existing.year1_amount = result.annual_amount
            existing.removed = False
            existing.source = BudgetSource.DEFAULT.value
            existing.default_rule_key = result.rule_key
        else:
            acct = accounts.get(target)
            line = BudgetLine(
                budget_line_id=_new_id("bl"),
                acquisition_id=acquisition_id,
                account_code=target,
                month_index=0,
                year1_amount=result.annual_amount,
                section=acct.section if acct else None,
                source=BudgetSource.DEFAULT.value,
                default_rule_key=result.rule_key,
            )
            session.add(line)
            by_account[target] = line


async def budget_exists(session: AsyncSession, acquisition_id: str) -> bool:
    return await _header(session, acquisition_id) is not None


async def apply_defaults(
    session: AsyncSession, acquisition_id: str, *, actor: str | None = None
) -> BudgetDoc:
    """Re-apply the defaults engine to the budget (used on a driver change so dependent defaults
    recompute). Manual lines are untouched; editing invalidates the lock."""
    await _ensure_header(session, acquisition_id)
    by_account = {
        bl.account_code: bl for bl in await _lines(session, acquisition_id) if bl.account_code
    }
    accounts = await _accounts(session)
    await _apply_defaults_lines(session, acquisition_id, by_account, accounts)
    _invalidate_lock(await _header(session, acquisition_id))
    await session.commit()
    return await get_budget(session, acquisition_id)


async def revert_to_default(
    session: AsyncSession, acquisition_id: str, line_id: str, *, actor: str | None
) -> BudgetDoc:
    """Clear a line's manual override and re-link it to its default rule (the non-destructive
    'revert' for the manual-sticks rule). Recomputes the line from the current drivers."""
    line = await session.get(BudgetLine, line_id)
    if line is None or line.acquisition_id != acquisition_id:
        raise BudgetError("line_not_found", "No such budget line.")
    if not line.default_rule_key:
        raise BudgetError("no_default", "This line has no default rule to revert to.")
    line.is_overridden = False
    line.overridden_by = None
    line.overridden_at = None
    line.removed = False
    await session.flush()
    return await apply_defaults(session, acquisition_id, actor=actor)


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
    the prior actual); (2) the defaults engine fills the rest — fixed/percent/per-unit/per-employee
    rules gap-fill GLs the actuals lack (Shield + the property-tax uplift supersede history). Never
    clobbers a human override."""
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

    await _apply_defaults_lines(session, acquisition_id, by_account, accounts)

    await session.commit()
    return await get_budget(session, acquisition_id)


async def apply_labor(
    session: AsyncSession, acquisition_id: str, amounts: dict[str, Decimal], *, actor: str | None
) -> None:
    """Write the Labor tab's computed year-one onto its GL budget lines (source=labor). Never
    clobbers a human override; FK-safe (skips GLs not in the chart). Caller commits."""
    await _ensure_header(session, acquisition_id)
    known = await _accounts(session)
    by_account = {
        bl.account_code: bl for bl in await _lines(session, acquisition_id) if bl.account_code
    }
    for code, amount in amounts.items():
        if code not in known:
            continue
        line = by_account.get(code)
        if line is None:
            line = BudgetLine(
                budget_line_id=_new_id("bl"),
                acquisition_id=acquisition_id,
                account_code=code,
                month_index=0,
                year1_amount=amount,
                section=known[code].section,
                source=BudgetSource.LABOR.value,
                default_rule_key="labor",
            )
            session.add(line)
            by_account[code] = line
        elif not line.is_overridden:  # a deliberate manual edit wins over the labor feed
            line.year1_amount = amount
            line.source = BudgetSource.LABOR.value
            line.default_rule_key = "labor"
    _invalidate_lock(await _header(session, acquisition_id))


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


async def reorder_lines(
    session: AsyncSession, acquisition_id: str, refs: list[BudgetLineRef], *, actor: str | None
) -> BudgetDoc:
    """Set the display order of budget lines (drag-to-reorder). Each ref is a stored ``line_id`` or
    an un-seeded GL ``account_code`` (materialized here, like a first edit). Assigns a dense
    ``sort_order`` in the given top-to-bottom order. Presentational only: it does not touch any
    amount or the NOI roll-up (which is section-based), so it's allowed even on a locked budget and
    doesn't invalidate the lock. Callers send one section's rows in their new order."""
    accounts = await _accounts(session)
    for i, ref in enumerate(refs):
        line = await _resolve_line(
            session, acquisition_id, line_id=ref.line_id, account_code=ref.account_code
        )
        if line is None:
            if ref.account_code is None or ref.account_code not in accounts:
                raise BudgetError("line_not_found", "Cannot reorder an unknown budget line.")
            acct = accounts[ref.account_code]
            line = BudgetLine(
                budget_line_id=_new_id("bl"),
                acquisition_id=acquisition_id,
                account_code=ref.account_code,
                month_index=0,
                section=acct.section,
                source=BudgetSource.ACTUALS.value,
            )
            session.add(line)
        line.sort_order = i
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

"""Operational-input service (defaults engine, Part 1): capture + edit the per-deal drivers.

Assembles the Operating Inputs panel (unit groups + headcount + electric), seeds it from the OM /
mapped data where present, and persists edits. Every value is editable; editing flips the field's
provenance to ``manual``. The dependent defaults (Part 2) read these drivers; nothing is guessed —
a missing driver surfaces a "needs input" flag instead.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..mapping import repository as mapping_repo
from ..models.acquisitions import Acquisition
from ..models.operating import (
    SOURCE_ACTUALS,
    SOURCE_MANUAL,
    SOURCE_NEEDS_INPUT,
    SOURCE_OM,
    OperationalInputs,
    UnitGroup,
)
from ..models.property import Unit
from ..schemas.operating import (
    OperatingDoc,
    OperatingPatch,
    UnitGroupCreate,
    UnitGroupPatch,
    UnitGroupRow,
)
from .budget import bucket_line_months
from .operating import (
    UNIT_TYPE_TO_CATEGORY,
    UnitGroupInput,
    billable_unit_total,
    default_billable,
    default_billable_for_added,
    units_need_input,
)

_ZERO = Decimal(0)
# The default billable categories seeded when a deal has no unit rows yet (tents non-billable).
_SEED_CATEGORIES: tuple[tuple[str, bool], ...] = (
    ("rv_pad", True),
    ("cabin", True),
    ("glamping", True),
    ("tent", False),
)


class OperatingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def _recompute_budget_defaults(
    session: AsyncSession, acquisition_id: str, actor: str | None
) -> None:
    """A driver changed (unit count / headcount / electric) → re-apply the budget defaults so the
    dependent lines recompute. Manual lines are untouched (manual sticks). No-op if no budget yet.
    Deferred import avoids a module-load cycle with budget_service."""
    from . import budget_service

    if await budget_service.budget_exists(session, acquisition_id):
        await budget_service.apply_defaults(session, acquisition_id, actor=actor)


async def _header(session: AsyncSession, acquisition_id: str) -> OperationalInputs | None:
    return await session.get(OperationalInputs, acquisition_id)


async def _groups(session: AsyncSession, acquisition_id: str) -> list[UnitGroup]:
    stmt = select(UnitGroup).where(UnitGroup.acquisition_id == acquisition_id)
    return list((await session.execute(stmt)).scalars().all())


async def _electric_prior_actual(session: AsyncSession, acquisition_id: str) -> Decimal | None:
    """The Electric line that comes through the budget — the mapped prior-year actual on the
    configured Electric account (605410). Annual-aware: a recap P&L's per-month columns are summed;
    an annual-only source (OM / non-recap P&L) uses the line amount. None if no electric is mapped.
    """
    code = settings.electric_account_code
    if code is None:
        return None
    total = _ZERO
    found = False
    for line in await mapping_repo.list_lines(session, acquisition_id):
        if line.account_code != code:
            continue
        months = bucket_line_months(line.raw_payload) if line.raw_payload else {}
        total += sum(months.values(), _ZERO) if months else (line.amount or _ZERO)
        found = True
    return total if found else None


def _to_doc(
    header: OperationalInputs | None,
    groups: list[UnitGroup],
    roster_headcount: int | None,
    budget_electric: Decimal | None,
) -> OperatingDoc:
    """Assemble the panel from stored state + the pure driver math (no DB). Headcount is NOT stored
    here — it's the Labor roster total (single source of truth), passed in read-only. Electric
    defaults live from the budget's Electric line (``budget_electric``) unless overridden."""
    ordered = sorted(groups, key=lambda g: (g.sort if g.sort is not None else 9999, g.category))
    rows = [
        UnitGroupRow(
            unit_group_id=g.unit_group_id,
            category=g.category,
            label=g.label,
            count=g.count,
            billable=g.billable,
            source=g.source,
            sort=g.sort,
        )
        for g in ordered
    ]
    inputs = [
        UnitGroupInput(category=g.category, count=g.count, billable=g.billable) for g in groups
    ]
    # Electric: a manual override wins; otherwise default live to the budget's Electric line; else
    # any seeded value (e.g. OM) so an unmapped electric line doesn't drop a captured number.
    if header is not None and header.electric_source == SOURCE_MANUAL:
        electric, electric_source = header.electric_annual, SOURCE_MANUAL
    elif budget_electric is not None:
        electric, electric_source = budget_electric, SOURCE_ACTUALS
    elif header is not None and header.electric_annual is not None:
        electric, electric_source = header.electric_annual, header.electric_source
    else:
        electric, electric_source = None, SOURCE_NEEDS_INPUT
    return OperatingDoc(
        unit_groups=rows,
        billable_unit_total=billable_unit_total(inputs),
        units_need_input=units_need_input(inputs),
        # Read-only: headcount comes from the Labor roster, never stored on Operating.
        employee_headcount=roster_headcount,
        headcount_source="labor" if roster_headcount is not None else SOURCE_NEEDS_INPUT,
        headcount_needs_input=roster_headcount is None,
        electric_annual=electric,
        electric_source=electric_source,
        electric_needs_input=electric is None,
    )


async def _roster_headcount(session: AsyncSession, acquisition_id: str) -> int | None:
    """The Labor roster total (SSOT). Reuses budget_service's canonical implementation; deferred
    import avoids a module-load cycle."""
    from . import budget_service

    return await budget_service.roster_headcount(session, acquisition_id)


async def get_operating(session: AsyncSession, acquisition_id: str) -> OperatingDoc:
    """Read the panel (no mutation; serves whatever's captured so far). Headcount = Labor roster."""
    return _to_doc(
        await _header(session, acquisition_id),
        await _groups(session, acquisition_id),
        await _roster_headcount(session, acquisition_id),
        await _electric_prior_actual(session, acquisition_id),
    )


async def _ensure_header(session: AsyncSession, acquisition_id: str) -> OperationalInputs:
    header = await _header(session, acquisition_id)
    if header is None:
        header = OperationalInputs(acquisition_id=acquisition_id)
        session.add(header)
    return header


async def _seed_unit_groups(session: AsyncSession, acquisition_id: str) -> None:
    """Seed unit groups from the mapped Unit rows (OM unit mix) where present, else the default
    billable categories as 'needs input'. Idempotent: a no-op once any group exists."""
    if await _groups(session, acquisition_id):
        return
    units = list(
        (await session.execute(select(Unit).where(Unit.acquisition_id == acquisition_id)))
        .scalars()
        .all()
    )
    # Aggregate the OM unit mix into billable-unit categories.
    by_category: dict[str, int | None] = {}
    for u in units:
        cat = UNIT_TYPE_TO_CATEGORY.get(u.unit_type.value, u.unit_type.value)
        if u.count is not None:
            by_category[cat] = (by_category.get(cat) or 0) + u.count
        else:
            by_category.setdefault(cat, None)

    sort = 0
    if by_category:
        for cat, count in by_category.items():
            session.add(
                UnitGroup(
                    unit_group_id=_new_id("ug"),
                    acquisition_id=acquisition_id,
                    category=cat,
                    count=count,
                    billable=default_billable(cat),
                    source=SOURCE_OM if count is not None else SOURCE_NEEDS_INPUT,
                    sort=sort,
                )
            )
            sort += 1
        return

    # No unit rows: seed the default categories (prompt for counts). If the OM gave a site_count,
    # put it on RV pads as the starting estimate; the user splits it across categories.
    acq = await session.get(Acquisition, acquisition_id)
    site_count = acq.site_count if acq else None
    for cat, billable in _SEED_CATEGORIES:
        count = site_count if cat == "rv_pad" else None
        session.add(
            UnitGroup(
                unit_group_id=_new_id("ug"),
                acquisition_id=acquisition_id,
                category=cat,
                count=count,
                billable=billable,
                source=SOURCE_OM if count is not None else SOURCE_NEEDS_INPUT,
                sort=sort,
            )
        )
        sort += 1


async def seed_operating(
    session: AsyncSession, acquisition_id: str, *, actor: str | None
) -> OperatingDoc:
    """Seed the panel idempotently: unit groups from the OM unit mix, electric from the mapped
    prior-year Electric actual. Headcount has no OM source, so it stays 'needs input'. Never
    clobbers a manual edit."""
    header = await _ensure_header(session, acquisition_id)
    await _seed_unit_groups(session, acquisition_id)
    if header.electric_source != SOURCE_MANUAL:
        prior = await _electric_prior_actual(session, acquisition_id)
        if prior is not None:
            header.electric_annual = prior
            header.electric_source = SOURCE_ACTUALS
    await session.commit()
    await _recompute_budget_defaults(session, acquisition_id, actor)
    return await get_operating(session, acquisition_id)


async def patch_operating(
    session: AsyncSession, acquisition_id: str, body: OperatingPatch, *, actor: str | None
) -> OperatingDoc:
    """Edit the electric driver (flips it to ``manual`` provenance). Headcount is not editable here
    — it's the Labor roster total (SSOT)."""
    header = await _ensure_header(session, acquisition_id)
    if body.electric_annual is not None:
        header.electric_annual = body.electric_annual
        header.electric_source = SOURCE_MANUAL
    if body.note is not None:
        header.note = body.note
    await session.commit()
    await _recompute_budget_defaults(session, acquisition_id, actor)
    return await get_operating(session, acquisition_id)


async def add_unit_group(
    session: AsyncSession, acquisition_id: str, body: UnitGroupCreate, *, actor: str | None
) -> OperatingDoc:
    """Add a unit group — a default category or a custom sub-type (defaults to billable)."""
    if not body.category.strip():
        raise OperatingError("missing_fields", "A unit group needs a category.")
    await _ensure_header(session, acquisition_id)
    existing = await _groups(session, acquisition_id)
    next_sort = 1 + max((g.sort or 0 for g in existing), default=0)
    billable = (
        body.billable if body.billable is not None else default_billable_for_added(body.category)
    )
    session.add(
        UnitGroup(
            unit_group_id=_new_id("ug"),
            acquisition_id=acquisition_id,
            category=body.category.strip(),
            label=body.label,
            count=body.count,
            billable=billable,
            source=SOURCE_MANUAL,
            sort=next_sort,
        )
    )
    await session.commit()
    await _recompute_budget_defaults(session, acquisition_id, actor)
    return await get_operating(session, acquisition_id)


async def _resolve_group(
    session: AsyncSession, acquisition_id: str, unit_group_id: str
) -> UnitGroup:
    group = await session.get(UnitGroup, unit_group_id)
    if group is None or group.acquisition_id != acquisition_id:
        raise OperatingError("not_found", "No such unit group.")
    return group


async def patch_unit_group(
    session: AsyncSession, acquisition_id: str, body: UnitGroupPatch, *, actor: str | None
) -> OperatingDoc:
    """Edit a unit group — any edit flips its source to ``manual``."""
    group = await _resolve_group(session, acquisition_id, body.unit_group_id)
    if body.category is not None:
        group.category = body.category.strip()
    if body.label is not None:
        group.label = body.label
    if body.count is not None:
        group.count = body.count
    if body.billable is not None:
        group.billable = body.billable
    group.source = SOURCE_MANUAL
    await session.commit()
    await _recompute_budget_defaults(session, acquisition_id, actor)
    return await get_operating(session, acquisition_id)


async def remove_unit_group(
    session: AsyncSession, acquisition_id: str, unit_group_id: str, *, actor: str | None
) -> OperatingDoc:
    """Remove a unit group outright (drivers recompute from the remaining groups)."""
    group = await _resolve_group(session, acquisition_id, unit_group_id)
    await session.delete(group)
    await session.commit()
    await _recompute_budget_defaults(session, acquisition_id, actor)
    return await get_operating(session, acquisition_id)

"""Labor plan service (design doc §5.5, Labor tab): CRUD the staffing positions, seed a default
scenario, and feed the computed totals into the budget — the Wages cluster (600140/600130/600155)
plus, for work campers, extended-stay revenue (400110) and the campsite credit (421300, contra).
Labor therefore flows budget → stabilized NOI → pro forma → promote via the existing path."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.labor import LaborPosition
from ..schemas.labor import (
    LaborDoc,
    LaborPositionCreate,
    LaborPositionPatch,
    LaborPositionRow,
    LaborTotalsOut,
)
from . import budget_service
from . import labor as engine

_ZERO = Decimal(0)
_FT_HOURS = Decimal(40)
_PT_HOURS = Decimal(20)
_FULL_YEAR_WEEKS = Decimal(52)

# Default staffing scenario: 1 GM + 1 front desk + 1 maintenance (full-time) + 1 part-time of the
# latter two. Rates/dates blank — the underwriter fills them; hours default from the type.
_DEFAULT_STAFFING: list[tuple[str, str, str]] = [
    ("general_manager", "full_time", "year_round"),
    ("front_desk", "full_time", "year_round"),
    ("maintenance", "full_time", "year_round"),
    ("front_desk", "part_time", "year_round"),
    ("maintenance", "part_time", "year_round"),
]
_ROLE_LABELS = {
    "general_manager": "General Manager",
    "front_desk": "Front Desk",
    "housekeeper": "Housekeeper",
    "maintenance": "Maintenance",
    "events_coordinator": "Events Coordinator",
}


class LaborError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _new_id() -> str:
    return f"lp_{uuid.uuid4().hex[:16]}"


def _context() -> engine.LaborContext:
    return engine.LaborContext(
        benefits_monthly_per_employee=settings.labor_benefits_monthly_per_employee,
        payroll_tax_pct=settings.labor_payroll_tax_pct,
    )


def _hours(p: LaborPosition) -> Decimal:
    if p.hours_per_week is not None:
        return p.hours_per_week
    return _PT_HOURS if p.employment_type == "part_time" else _FT_HOURS


def _weeks(p: LaborPosition) -> Decimal:
    if p.start_date is not None and p.end_date is not None:
        return engine.active_weeks(p.start_date, p.end_date)
    return _FULL_YEAR_WEEKS if p.season == "year_round" else _ZERO


def _to_engine(p: LaborPosition) -> engine.LaborPosition:
    return engine.LaborPosition(
        headcount=p.headcount or 1,
        hours_per_week=_hours(p),
        hourly_rate=p.hourly_rate or _ZERO,
        weeks=_weeks(p),
        benefits_eligible=p.benefits_eligible,
        is_work_camper=p.is_work_camper,
        site_weekly_rate=p.site_weekly_rate or _ZERO,
        campsite_credit_weekly=p.campsite_credit_weekly or _ZERO,
    )


async def _positions(session: AsyncSession, acquisition_id: str) -> list[LaborPosition]:
    stmt = (
        select(LaborPosition)
        .where(LaborPosition.acquisition_id == acquisition_id)
        .order_by(LaborPosition.sort, LaborPosition.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


def _name(p: LaborPosition) -> str:
    return p.label or _ROLE_LABELS.get(p.role, p.role)


def _row(p: LaborPosition) -> LaborPositionRow:
    ep = _to_engine(p)
    return LaborPositionRow(
        position_id=p.position_id,
        role=p.role,
        name=_name(p),
        label=p.label,
        employment_type=p.employment_type,
        season=p.season,
        headcount=p.headcount or 1,
        hours_per_week=_hours(p),
        hourly_rate=p.hourly_rate,
        is_work_camper=p.is_work_camper,
        benefits_eligible=p.benefits_eligible,
        site_weekly_rate=p.site_weekly_rate,
        campsite_credit_weekly=p.campsite_credit_weekly,
        start_date=p.start_date,
        end_date=p.end_date,
        weeks=ep.weeks,
        wages=engine.position_wages(ep),
        note=p.note,
    )


def _amounts(totals: engine.LaborTotals) -> dict[str, Decimal]:
    """Map the roll-up to GL year-one amounts. The campsite credit is stored NEGATIVE — it's a
    contra-revenue (discount) that reduces revenue."""
    out: dict[str, Decimal] = {}
    if settings.labor_wages_account_code:
        out[settings.labor_wages_account_code] = totals.wages
    if settings.labor_benefits_account_code:
        out[settings.labor_benefits_account_code] = totals.benefits
    if settings.labor_payroll_tax_account_code:
        out[settings.labor_payroll_tax_account_code] = totals.payroll_tax
    if settings.labor_extended_stay_account_code:
        out[settings.labor_extended_stay_account_code] = totals.extended_stay_revenue
    if settings.labor_work_camper_credit_account_code:
        out[settings.labor_work_camper_credit_account_code] = -totals.work_camper_credit
    return out


async def _prior_labor(session: AsyncSession, acquisition_id: str) -> Decimal:
    """Prior-year labor = mapped prior actuals for the wages-cluster GLs."""
    prior = await budget_service._prior_actuals(session, acquisition_id)
    codes = {
        c
        for c in (
            settings.labor_wages_account_code,
            settings.labor_benefits_account_code,
            settings.labor_payroll_tax_account_code,
        )
        if c
    }
    return sum((prior.get(c, _ZERO) for c in codes), _ZERO)


async def _feed_budget(session: AsyncSession, acquisition_id: str, *, actor: str | None) -> None:
    totals = engine.roll_up(
        [_to_engine(p) for p in await _positions(session, acquisition_id)], _context()
    )
    await budget_service.apply_labor(session, acquisition_id, _amounts(totals), actor=actor)


async def get_labor(session: AsyncSession, acquisition_id: str) -> LaborDoc:
    positions = await _positions(session, acquisition_id)
    totals = engine.roll_up([_to_engine(p) for p in positions], _context())
    return LaborDoc(
        positions=[_row(p) for p in positions],
        totals=LaborTotalsOut(
            wages=totals.wages,
            benefits=totals.benefits,
            payroll_tax=totals.payroll_tax,
            extended_stay_revenue=totals.extended_stay_revenue,
            work_camper_credit=totals.work_camper_credit,
            total_cash_labor=totals.total_cash_labor,
            prior_labor=await _prior_labor(session, acquisition_id),
        ),
    )


async def _next_sort(session: AsyncSession, acquisition_id: str) -> int:
    positions = await _positions(session, acquisition_id)
    return (max((p.sort or 0) for p in positions) + 10) if positions else 10


async def add_position(
    session: AsyncSession, acquisition_id: str, body: LaborPositionCreate, *, actor: str | None
) -> LaborDoc:
    session.add(
        LaborPosition(
            position_id=_new_id(),
            acquisition_id=acquisition_id,
            role=body.role,
            label=body.label,
            employment_type=body.employment_type or "full_time",
            season=body.season or "year_round",
            headcount=body.headcount or 1,
            hours_per_week=body.hours_per_week,
            hourly_rate=body.hourly_rate,
            is_work_camper=bool(body.is_work_camper),
            benefits_eligible=bool(body.benefits_eligible),
            site_weekly_rate=body.site_weekly_rate,
            campsite_credit_weekly=body.campsite_credit_weekly,
            start_date=body.start_date,
            end_date=body.end_date,
            sort=await _next_sort(session, acquisition_id),
            note=body.note,
        )
    )
    await session.flush()
    await _feed_budget(session, acquisition_id, actor=actor)
    await session.commit()
    return await get_labor(session, acquisition_id)


async def patch_position(
    session: AsyncSession, acquisition_id: str, body: LaborPositionPatch, *, actor: str | None
) -> LaborDoc:
    p = await session.get(LaborPosition, body.position_id)
    if p is None or p.acquisition_id != acquisition_id:
        raise LaborError("not_found", "No such position.")
    for key, value in body.model_dump(exclude_unset=True, exclude={"position_id"}).items():
        setattr(p, key, value)
    await session.flush()
    await _feed_budget(session, acquisition_id, actor=actor)
    await session.commit()
    return await get_labor(session, acquisition_id)


async def remove_position(
    session: AsyncSession, acquisition_id: str, position_id: str, *, actor: str | None
) -> LaborDoc:
    p = await session.get(LaborPosition, position_id)
    if p is None or p.acquisition_id != acquisition_id:
        raise LaborError("not_found", "No such position.")
    await session.delete(p)
    await session.flush()
    await _feed_budget(session, acquisition_id, actor=actor)
    await session.commit()
    return await get_labor(session, acquisition_id)


async def seed_default_staffing(
    session: AsyncSession, acquisition_id: str, *, actor: str | None
) -> LaborDoc:
    """Create the default staffing scenario (idempotent — no-op if positions already exist)."""
    if not await _positions(session, acquisition_id):
        sort = 0
        for role, etype, season in _DEFAULT_STAFFING:
            sort += 10
            session.add(
                LaborPosition(
                    position_id=_new_id(),
                    acquisition_id=acquisition_id,
                    role=role,
                    employment_type=etype,
                    season=season,
                    headcount=1,
                    is_work_camper=False,
                    benefits_eligible=etype == "full_time",  # FT eligible by default; PT not
                    sort=sort,
                )
            )
        await session.flush()
        await _feed_budget(session, acquisition_id, actor=actor)
        await session.commit()
    return await get_labor(session, acquisition_id)

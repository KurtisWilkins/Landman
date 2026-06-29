"""Labor plan schemas (design doc §5.5, Labor tab)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class LaborPositionRow(BaseModel):
    """One planned position with its computed weeks + cash wages (work campers draw $0 cash)."""

    position_id: str
    role: str  # general_manager | front_desk | housekeeper | maintenance | events_coordinator | …
    name: str
    label: str | None = None
    employment_type: str  # full_time | part_time
    season: str  # year_round | seasonal
    headcount: int = 1
    hours_per_week: Decimal | None = None
    hourly_rate: Decimal | None = None
    is_work_camper: bool = False
    benefits_eligible: bool = False
    site_weekly_rate: Decimal | None = None
    campsite_credit_weekly: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None
    weeks: Decimal
    wages: Decimal
    source: str = "manual"  # om | default | manual
    needs_wage: bool = False  # required wage missing (not a work camper, no hourly rate)
    note: str | None = None


class LaborTotalsOut(BaseModel):
    wages: Decimal  # → 600140
    benefits: Decimal  # → 600130
    payroll_tax: Decimal  # → 600155
    extended_stay_revenue: Decimal  # → 400110 (work campers)
    work_camper_credit: Decimal  # → 421300 (work campers, contra-revenue)
    total_cash_labor: Decimal  # wages + benefits + payroll_tax (the expense the budget sees)
    prior_labor: Decimal  # prior-year wages-cluster actuals from the mapped P&L
    headcount: int  # authoritative roster headcount (Σ positions) — the app-wide SSOT


class LaborDoc(BaseModel):
    positions: list[LaborPositionRow] = Field(default_factory=list)
    totals: LaborTotalsOut


class StaffingRoleIn(BaseModel):
    """One OM-proposed staffing line passed to the roster seed."""

    role: str
    count: int | None = None
    hourly_rate: Decimal | None = None


class LaborSeedRequest(BaseModel):
    """Optional OM staffing to seed the roster from; empty → the default scenario."""

    staffing: list[StaffingRoleIn] = Field(default_factory=list)


class LaborPositionCreate(BaseModel):
    role: str
    label: str | None = None
    employment_type: str | None = None  # default full_time
    season: str | None = None  # default year_round
    headcount: int | None = None
    hours_per_week: Decimal | None = None
    hourly_rate: Decimal | None = None
    is_work_camper: bool | None = None
    benefits_eligible: bool | None = None
    site_weekly_rate: Decimal | None = None
    campsite_credit_weekly: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None
    note: str | None = None


class LaborPositionPatch(BaseModel):
    position_id: str
    role: str | None = None
    label: str | None = None
    employment_type: str | None = None
    season: str | None = None
    headcount: int | None = None
    hours_per_week: Decimal | None = None
    hourly_rate: Decimal | None = None
    is_work_camper: bool | None = None
    benefits_eligible: bool | None = None
    site_weekly_rate: Decimal | None = None
    campsite_credit_weekly: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None
    note: str | None = None

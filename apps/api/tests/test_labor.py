"""Pure labor-plan math (§5.5) — worked examples, no DB."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from rjacq.underwriting.labor import (
    LaborContext,
    LaborPosition,
    active_weeks,
    position_benefits,
    position_wages,
    roll_up,
)


def _pos(**kw: Any) -> LaborPosition:
    base: dict[str, Any] = {
        "headcount": 1,
        "hours_per_week": Decimal("40"),
        "hourly_rate": Decimal("28"),
        "weeks": Decimal("52"),
        "benefits_eligible": False,
        "is_work_camper": False,
        "site_weekly_rate": Decimal("0"),
        "campsite_credit_weekly": Decimal("0"),
    }
    base.update(kw)
    return LaborPosition(**base)


def test_active_weeks() -> None:
    assert active_weeks(date(2026, 1, 1), date(2026, 12, 31)) == Decimal(364) / Decimal(7)  # 52
    assert active_weeks(None, date(2026, 12, 31)) == Decimal(0)
    assert active_weeks(date(2026, 12, 31), date(2026, 1, 1)) == Decimal(0)  # end before start


def test_position_wages_ft_pt_and_work_camper() -> None:
    assert position_wages(_pos(hours_per_week=Decimal("40"), hourly_rate=Decimal("28"))) == Decimal(
        "58240"
    )  # 40 × 28 × 52
    pt = _pos(hours_per_week=Decimal("20"), hourly_rate=Decimal("16"), weeks=Decimal("20"))
    assert position_wages(pt) == Decimal("6400")  # 20 × 16 × 20
    wc = _pos(is_work_camper=True, hours_per_week=Decimal("20"), hourly_rate=Decimal("17"))
    assert position_wages(wc) == Decimal("0")  # work camper draws no cash wage


def test_position_benefits_flat_monthly() -> None:
    ctx = LaborContext(
        benefits_monthly_per_employee=Decimal("500"), payroll_tax_pct=Decimal("0.10")
    )
    assert position_benefits(_pos(benefits_eligible=True), ctx) == Decimal("6000")  # 500 × 12 mo
    assert position_benefits(_pos(benefits_eligible=False), ctx) == Decimal("0")
    no_cfg = LaborContext(benefits_monthly_per_employee=None, payroll_tax_pct=None)
    assert position_benefits(_pos(benefits_eligible=True), no_cfg) == Decimal("0")


def test_roll_up_full_plan() -> None:
    ctx = LaborContext(
        benefits_monthly_per_employee=Decimal("500"), payroll_tax_pct=Decimal("0.10")
    )
    positions = [
        _pos(hourly_rate=Decimal("28"), benefits_eligible=True),  # 58240 wages + 6000 benefits
        _pos(  # work camper: 6000 revenue + 6000 credit, no cash wage
            is_work_camper=True,
            weeks=Decimal("20"),
            site_weekly_rate=Decimal("300"),
            campsite_credit_weekly=Decimal("300"),
        ),
    ]
    t = roll_up(positions, ctx)
    assert t.wages == Decimal("58240")
    assert t.benefits == Decimal("6000")
    assert t.payroll_tax == Decimal("5824")  # 58240 × 0.10
    assert t.extended_stay_revenue == Decimal("6000")
    assert t.work_camper_credit == Decimal("6000")
    assert t.total_cash_labor == Decimal("70064")  # 58240 + 6000 + 5824


# ── Headcount SSOT + OM role normalization (pure) ────────────────────────────


def test_total_headcount_sums_counts_missing_is_one() -> None:
    from rjacq.underwriting.labor import total_headcount

    assert total_headcount([1, 1, 1]) == 3
    assert total_headcount([2, None, 3]) == 6  # a missing count counts as 1
    assert total_headcount([]) == 0


def test_normalize_role_maps_titles_else_custom() -> None:
    from rjacq.underwriting.labor import normalize_role

    assert normalize_role("General Manager") == "general_manager"
    assert normalize_role("Front Desk Clerk") == "front_desk"
    assert normalize_role("Housekeeping") == "housekeeper"
    assert normalize_role("Groundskeeper") == "maintenance"
    assert normalize_role("Activities Director") == "events_coordinator"
    assert normalize_role("Executive Chef") == "custom"

"""Operational-input schemas (defaults engine, Part 1) — the per-deal driver capture panel.

Drivers: the billable unit mix (per-unit R&M), the electric expense (utility bill-back), and
employee headcount (payroll budget). Every value is editable; ``*_needs_input`` flags surface the
"can't compute the dependent default yet" prompts.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class UnitGroupRow(BaseModel):
    """One unit grouping in the capture grid."""

    unit_group_id: str
    category: str  # rv_pad | cabin | glamping | tent | <custom sub-type>
    label: str | None = None
    count: int | None = None  # None = not captured yet (needs input)
    billable: bool = True  # counts toward the per-unit drivers (tents False)
    source: str  # om | manual | needs_input
    sort: int | None = None


class OperatingDoc(BaseModel):
    """The Operating Inputs panel: the unit groups + headcount + electric, with derived driver
    totals and the needs-input flags that gate the dependent defaults."""

    unit_groups: list[UnitGroupRow] = Field(default_factory=list)
    billable_unit_total: int = 0  # RV pads + cabins + glamping (tents excluded)
    units_need_input: bool = True  # a billable group is missing its count (or none exist)

    employee_headcount: int | None = None
    headcount_source: str = "needs_input"
    headcount_needs_input: bool = True

    electric_annual: Decimal | None = None
    electric_source: str = "needs_input"
    electric_needs_input: bool = True


class UnitGroupCreate(BaseModel):
    """Add a unit group — a default category or a custom sub-type."""

    category: str
    label: str | None = None
    count: int | None = None
    billable: bool | None = None  # default: True for a normal category (caller may override)


class UnitGroupPatch(BaseModel):
    """Edit a unit group's count / billable flag / label (flips its source to manual)."""

    unit_group_id: str
    category: str | None = None
    label: str | None = None
    count: int | None = None
    billable: bool | None = None


class OperatingPatch(BaseModel):
    """Edit the headcount and/or electric driver (flips the edited field's source to manual)."""

    employee_headcount: int | None = None
    electric_annual: Decimal | None = None
    note: str | None = None

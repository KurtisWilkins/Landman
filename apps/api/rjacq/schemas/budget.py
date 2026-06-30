"""Year-one budget schemas (design doc §5.5, §9) — the two-column annual grid."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class BudgetRow(BaseModel):
    """One grid line: a canonical GL or a custom line, with an editable prior-year and year-one
    amount + provenance for each column."""

    line_id: str | None = None  # None for a prior-actuals row not yet stored (created on edit)
    account_code: str | None = None  # None for a custom (non-GL) line
    custom_label: str | None = None
    name: str
    section: str | None = None  # Income | Expense | (other)
    # Canonical-chart hierarchy so the Budget tab can nest the row under its group/sub-group.
    parent_code: str | None = None  # the GL group this leaf rolls into (None for custom lines)
    is_contra: bool = False  # sign-preserving negative offset (render in parentheses)
    tier: str | None = None  # core | rare (drives the optional "hide rare" toggle)
    source: str  # actuals | default | placeholder | custom | edited (year-one provenance)
    prior_annual: Decimal
    year1_annual: Decimal
    var_abs: Decimal
    var_pct: Decimal | None = None
    is_overridden: bool = False  # year-one edited
    prior_overridden: bool = False  # prior edited (corrects an upload)
    removed: bool = False  # dropped from the year-one projection (prior kept as reference)
    flagged_for_promotion: bool = False  # custom line to add to the GL chart later
    # True when this line was produced by a default rule and has since been manually edited — so the
    # UI can offer "revert to default" (the manual-sticks escape hatch).
    revertible: bool = False
    note: str | None = None


class BudgetTotals(BaseModel):
    prior_revenue: Decimal
    year1_revenue: Decimal
    prior_opex: Decimal
    year1_opex: Decimal
    prior_noi: Decimal
    year1_noi: Decimal


class BudgetGroup(BaseModel):
    """A roll-up subtotal for a chart group / sub-group / section header, mirroring the source's
    "Total - {code} - {name}" rows. Computed server-side by the pure ``roll_up_tree`` so the Budget
    tab renders the numbers without re-deriving any math. Present for every group that has at least
    one budget row beneath it."""

    code: str
    name: str
    level: str  # section | major_group | subgroup
    section: str | None = None  # Income | Expense | (other)
    parent_code: str | None = None
    prior_annual: Decimal
    year1_annual: Decimal
    var_abs: Decimal


class BudgetDoc(BaseModel):
    status: str  # draft | locked
    rows: list[BudgetRow] = Field(default_factory=list)
    # Group/sub-group subtotals (the "Total - …" rows) for the collapsible hierarchy.
    groups: list[BudgetGroup] = Field(default_factory=list)
    totals: BudgetTotals
    placeholder_count: int = 0  # unresolved "to review" lines (block the lock)
    unmapped_count: int = 0  # seller lines still unmapped (block the lock)


class BudgetLinePatch(BaseModel):
    """Edit a line's prior and/or year-one amount (by line_id, or by account_code for a
    not-yet-seeded GL row). Year-one edits flip the line to a human override."""

    line_id: str | None = None
    account_code: str | None = None
    prior_amount: Decimal | None = None
    year1_amount: Decimal | None = None
    note: str | None = None


class BudgetLineCreate(BaseModel):
    """Add a row: a canonical GL (account_code) or a custom line (custom_label + section)."""

    account_code: str | None = None
    custom_label: str | None = None
    section: str | None = None  # required for a custom line: Income | Expense
    prior_amount: Decimal | None = None
    year1_amount: Decimal | None = None


class BudgetLineRef(BaseModel):
    """A reference to one budget row for reordering: its stored ``line_id``, or an un-seeded GL
    ``account_code`` (materialized on reorder)."""

    line_id: str | None = None
    account_code: str | None = None


class BudgetReorder(BaseModel):
    """Set the display order of a section's rows (drag-to-reorder): the rows in their new
    top-to-bottom order. Presentational only — the NOI roll-up is section-based."""

    lines: list[BudgetLineRef] = Field(default_factory=list)

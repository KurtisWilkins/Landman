"""Pure budget-defaults rule engine (defaults engine, Part 2).

A typed, configurable rule library: each rule has a TYPE, a value/driver, and a target GL. The
math is pure + Decimal so it's unit-tested with worked examples like the pro-forma / promote /
budget engines. ``RULE_LIBRARY`` is the seed/reset spec (the sanctioned defaults the user gave us);
a global, admin-editable store overlays it so the percentages/rates/fixed amounts are centrally
configurable — but the *logic* here never bakes in a number (CLAUDE.md rule #2).

Rule types:
  - PERCENT_OF_GROSS_REVENUE — rate × projected operating revenue (insurance, CC processing,
    utilities). A rate edited outside its recommended band emits a soft warning (never blocks).
  - PERCENT_OF_LINE — rate × a driver line. The utility bill-back is 62% of electric, modeled as a
    **contra-expense** (``is_income_offset``): the amount is posted NEGATIVE so it nets down the
    utilities bucket rather than adding revenue (→ 605415 Utility Recovery).
  - PER_UNIT_ANNUAL — $/billable unit (RV pads + cabins + glamping; tents excluded). Needs the unit
    counts captured first, else it reports "needs input" rather than guessing.
  - PRIOR_YEAR_UPLIFT — prior-year actual × a multiplier (property taxes ×1.30). A flagged
    placeholder (``must_fix``) — a reassessment, not a real default.
  - FIXED — a flat monthly or annual amount (Shield, PPC, SEO, active-management marketing, call
    center).
  - PER_EMPLOYEE_MONTH — $/employee/month × headcount × 12 (the payroll budget allocation — a
    budgeted amount, not actual wages, posted to its own GL).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

_MONTHS = Decimal(12)


class RuleType(str, Enum):
    PERCENT_OF_GROSS_REVENUE = "percent_of_gross_revenue"
    PERCENT_OF_LINE = "percent_of_line"
    PER_UNIT_ANNUAL = "per_unit_annual"
    PRIOR_YEAR_UPLIFT = "prior_year_uplift"
    FIXED = "fixed"
    PER_EMPLOYEE_MONTH = "per_employee_month"


@dataclass(frozen=True)
class RuleSpec:
    """One default rule. ``value`` meaning depends on ``rule_type``: a rate (percent types), a
    per-unit dollar amount, a prior-year multiplier, a fixed dollar amount, or a per-employee
    monthly dollar amount. Amounts/rates live here as *data* (and are DB-overridable), never as
    literals in the compute logic."""

    rule_key: str
    label: str
    rule_type: RuleType
    value: Decimal
    target_account_code: str
    basis: str = "annual"  # FIXED only: "annual" | "monthly"
    is_income_offset: bool = False  # post the computed amount NEGATIVE (contra-expense)
    # True = supersede a mapped actual on this exact account (Shield ignores history; the property-
    # tax uplift consumes-and-replaces the prior). False = gap-fill only (don't clobber seller
    # actuals; for a coarse/parent target, also skip if the subtree already has actuals).
    overrides_actuals: bool = False
    driver_account_code: str | None = None  # PRIOR_YEAR_UPLIFT: which prior-year line drives it
    soft_min: Decimal | None = None  # recommended-band floor (PERCENT_* rates)
    soft_max: Decimal | None = None  # recommended-band ceiling
    must_fix: bool = False  # surface a persistent "must fix" badge (placeholder rule)
    enabled: bool = True


@dataclass(frozen=True)
class DriverContext:
    """The per-deal drivers a rule may read (assembled by the service from operational_inputs +
    the budget). Any None/incomplete driver yields a NeedsInput rather than a guessed number."""

    gross_revenue: Decimal | None = None  # projected operating revenue base (excludes offsets)
    electric_annual: Decimal | None = None  # utility bill-back driver
    billable_units: int | None = None  # RV pads + cabins + glamping (tents excluded)
    units_complete: bool = False  # every billable group has a captured count
    headcount: int | None = None  # payroll-budget driver
    prior_year: dict[str, Decimal] | None = None  # account_code → prior-year annual actual


@dataclass(frozen=True)
class DefaultComputation:
    """A computed default line. ``annual_amount`` is **signed** — negative for a contra-expense
    offset (the bill-back)."""

    rule_key: str
    label: str
    target_account_code: str
    annual_amount: Decimal
    explain: str
    must_fix: bool = False
    soft_warning: str | None = None


@dataclass(frozen=True)
class NeedsInput:
    """A rule that can't compute yet because a driver hasn't been captured."""

    rule_key: str
    label: str
    target_account_code: str
    missing: str


def _soft_warning(spec: RuleSpec) -> str | None:
    """A non-blocking flag when an edited rate falls outside its recommended band."""
    if spec.soft_min is not None and spec.value < spec.soft_min:
        return f"{spec.value:%} is below the recommended {spec.soft_min:%}–{spec.soft_max:%} range"
    if spec.soft_max is not None and spec.value > spec.soft_max:
        return f"{spec.value:%} is above the recommended {spec.soft_min:%}–{spec.soft_max:%} range"
    return None


def compute_default(spec: RuleSpec, ctx: DriverContext) -> DefaultComputation | NeedsInput | None:
    """Evaluate one rule against the drivers. Returns the computed (signed) annual line, a
    NeedsInput when a required driver is missing, or None when the rule is disabled."""
    if not spec.enabled:
        return None

    def computed(amount: Decimal, explain: str) -> DefaultComputation:
        signed = -amount if spec.is_income_offset else amount
        return DefaultComputation(
            rule_key=spec.rule_key,
            label=spec.label,
            target_account_code=spec.target_account_code,
            annual_amount=signed,
            explain=explain,
            must_fix=spec.must_fix,
            soft_warning=_soft_warning(spec),
        )

    def needs(missing: str) -> NeedsInput:
        return NeedsInput(spec.rule_key, spec.label, spec.target_account_code, missing)

    if spec.rule_type is RuleType.PERCENT_OF_GROSS_REVENUE:
        if ctx.gross_revenue is None:
            return needs("projected gross revenue")
        amount = ctx.gross_revenue * spec.value
        return computed(amount, f"{spec.value:%} of ${ctx.gross_revenue:,.0f} gross revenue")

    if spec.rule_type is RuleType.PERCENT_OF_LINE:
        # The utility bill-back drives off the captured electric expense.
        if ctx.electric_annual is None:
            return needs("electric expense")
        amount = ctx.electric_annual * spec.value
        sign = " (contra-expense, posted negative)" if spec.is_income_offset else ""
        return computed(amount, f"{spec.value:%} of ${ctx.electric_annual:,.0f} electric{sign}")

    if spec.rule_type is RuleType.PER_UNIT_ANNUAL:
        if ctx.billable_units is None or not ctx.units_complete:
            return needs("billable unit counts")
        amount = Decimal(ctx.billable_units) * spec.value
        return computed(amount, f"${spec.value} × {ctx.billable_units} billable units")

    if spec.rule_type is RuleType.PRIOR_YEAR_UPLIFT:
        account = spec.driver_account_code or spec.target_account_code
        prior = (ctx.prior_year or {}).get(account)
        if prior is None:
            return needs(f"prior-year {spec.label.lower()}")
        amount = prior * spec.value
        return computed(amount, f"prior-year ${prior:,.0f} × {spec.value} uplift")

    if spec.rule_type is RuleType.FIXED:
        amount = spec.value if spec.basis == "annual" else spec.value * _MONTHS
        unit = "/yr" if spec.basis == "annual" else "/mo"
        return computed(amount, f"fixed ${spec.value}{unit}")

    if spec.rule_type is RuleType.PER_EMPLOYEE_MONTH:
        if ctx.headcount is None:
            return needs("employee headcount")
        amount = spec.value * Decimal(ctx.headcount) * _MONTHS
        return computed(
            amount,
            f"${spec.value}/employee/mo × {ctx.headcount} employees × 12 (budget allocation)",
        )

    return None  # pragma: no cover - exhaustive above


# ── The seed/reset library (the confirmed default values) ───────────────────────────────────────
# Centrally configurable: these are the canonical defaults; the admin store overlays them globally.
# Target GL codes are the RJourney chart (§8.5); 600145 (payroll budget) + 600220 (call center) are
# additive homes for this engine.
RULE_LIBRARY: tuple[RuleSpec, ...] = (
    RuleSpec(
        "insurance_pct", "Insurance", RuleType.PERCENT_OF_GROSS_REVENUE, Decimal("0.03"), "607100"
    ),
    RuleSpec(
        "cc_processing_pct",
        "Credit card processing",
        RuleType.PERCENT_OF_GROSS_REVENUE,
        Decimal("0.025"),
        "600700",
    ),
    RuleSpec(
        "utilities_pct",
        "Utilities",
        RuleType.PERCENT_OF_GROSS_REVENUE,
        Decimal("0.175"),
        "605400",
        soft_min=Decimal("0.15"),
        soft_max=Decimal("0.20"),
    ),
    RuleSpec(
        "utility_billback",
        "Utility bill-back",
        RuleType.PERCENT_OF_LINE,
        Decimal("0.62"),
        "605415",
        is_income_offset=True,
    ),
    RuleSpec(
        "repairs_maintenance",
        "Repairs & maintenance",
        RuleType.PER_UNIT_ANNUAL,
        Decimal("275"),
        "605100",
    ),
    RuleSpec(
        "property_tax_uplift",
        "Property taxes",
        RuleType.PRIOR_YEAR_UPLIFT,
        Decimal("1.30"),
        "607000",
        driver_account_code="607000",
        must_fix=True,
        overrides_actuals=True,
    ),
    RuleSpec(
        "shield",
        "Shield (PMS)",
        RuleType.FIXED,
        Decimal("1000"),
        "600410",
        basis="monthly",
        overrides_actuals=True,
    ),
    RuleSpec("ppc", "PPC", RuleType.FIXED, Decimal("12000"), "600225", basis="annual"),
    RuleSpec(
        "seo_marketing",
        "SEO / subscription marketing",
        RuleType.FIXED,
        Decimal("850"),
        "601010",
        basis="monthly",
    ),
    RuleSpec(
        "active_mgmt_marketing",
        "Active management marketing",
        RuleType.FIXED,
        Decimal("825"),
        "600210",
        basis="monthly",
    ),
    RuleSpec(
        "call_center", "Call center", RuleType.FIXED, Decimal("750"), "600220", basis="monthly"
    ),
    RuleSpec(
        "payroll_budget",
        "Payroll budget allocation",
        RuleType.PER_EMPLOYEE_MONTH,
        Decimal("85"),
        "600145",
    ),
)

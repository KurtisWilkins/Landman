"""Pure budget-defaults rule engine — worked examples for all six rule types (no DB).

These are correctness-critical (the engine autofills real underwriting line items), so each rule
type is pinned to a worked example, plus the bill-back sign, the soft warning, the must-fix flag,
and the needs-input gates.
"""

from __future__ import annotations

from decimal import Decimal

from rjacq.underwriting.defaults_rules import (
    RULE_LIBRARY,
    DefaultComputation,
    DriverContext,
    NeedsInput,
    RuleSpec,
    RuleType,
    compute_default,
)


def _rule(key: str) -> RuleSpec:
    return next(r for r in RULE_LIBRARY if r.rule_key == key)


def _amount(spec: RuleSpec, ctx: DriverContext) -> Decimal:
    out = compute_default(spec, ctx)
    assert isinstance(out, DefaultComputation), out
    return out.annual_amount


# ── PERCENT_OF_GROSS_REVENUE ─────────────────────────────────────────────────


def test_insurance_3pct_of_gross() -> None:
    assert _amount(
        _rule("insurance_pct"), DriverContext(gross_revenue=Decimal("1000000"))
    ) == Decimal("30000.00")


def test_cc_processing_2_5pct_of_gross() -> None:
    assert _amount(
        _rule("cc_processing_pct"), DriverContext(gross_revenue=Decimal("1000000"))
    ) == Decimal("25000.000")


def test_utilities_17_5pct_within_band_no_warning() -> None:
    out = compute_default(_rule("utilities_pct"), DriverContext(gross_revenue=Decimal("1000000")))
    assert isinstance(out, DefaultComputation)
    assert out.annual_amount == Decimal("175000.000")
    assert out.soft_warning is None  # 17.5% is inside 15–20%


def test_utilities_rate_outside_band_soft_warns_but_still_computes() -> None:
    edited = RuleSpec(
        "utilities_pct",
        "Utilities",
        RuleType.PERCENT_OF_GROSS_REVENUE,
        Decimal("0.22"),
        "605400",
        soft_min=Decimal("0.15"),
        soft_max=Decimal("0.20"),
    )
    out = compute_default(edited, DriverContext(gross_revenue=Decimal("1000000")))
    assert isinstance(out, DefaultComputation)
    assert out.annual_amount == Decimal("220000.00")  # not blocked
    assert out.soft_warning is not None and "above" in out.soft_warning


def test_percent_of_gross_needs_revenue() -> None:
    assert isinstance(compute_default(_rule("insurance_pct"), DriverContext()), NeedsInput)


# ── PERCENT_OF_LINE — utility bill-back (contra-expense) ─────────────────────


def test_billback_62pct_of_electric_is_negative_contra() -> None:
    out = compute_default(
        _rule("utility_billback"), DriverContext(electric_annual=Decimal("48000"))
    )
    assert isinstance(out, DefaultComputation)
    # 62% × 48,000 = 29,760, posted NEGATIVE (nets down the utilities bucket).
    assert out.annual_amount == Decimal("-29760.00")
    assert out.target_account_code == "605415"
    assert "contra-expense" in out.explain


def test_billback_needs_electric() -> None:
    assert isinstance(compute_default(_rule("utility_billback"), DriverContext()), NeedsInput)


# ── PER_UNIT_ANNUAL — repairs & maintenance ─────────────────────────────────


def test_rm_275_per_billable_unit() -> None:
    ctx = DriverContext(billable_units=132, units_complete=True)
    assert _amount(_rule("repairs_maintenance"), ctx) == Decimal("36300")


def test_rm_needs_input_when_counts_incomplete() -> None:
    ctx = DriverContext(billable_units=120, units_complete=False)  # a billable group lacks a count
    out = compute_default(_rule("repairs_maintenance"), ctx)
    assert isinstance(out, NeedsInput) and "unit" in out.missing


# ── PRIOR_YEAR_UPLIFT — property taxes (placeholder, must fix) ───────────────


def test_property_tax_130pct_uplift_flagged_must_fix() -> None:
    out = compute_default(
        _rule("property_tax_uplift"), DriverContext(prior_year={"607000": Decimal("50000")})
    )
    assert isinstance(out, DefaultComputation)
    assert out.annual_amount == Decimal("65000.00")  # 50,000 × 1.30
    assert out.must_fix is True


def test_property_tax_needs_prior() -> None:
    out = compute_default(_rule("property_tax_uplift"), DriverContext(prior_year={}))
    assert isinstance(out, NeedsInput)


# ── FIXED — shield / ppc / seo / active-mgmt / call center ───────────────────


def test_fixed_monthly_annualizes_x12() -> None:
    assert _amount(_rule("shield"), DriverContext()) == Decimal("12000")  # 1,000/mo
    assert _amount(_rule("seo_marketing"), DriverContext()) == Decimal("10200")  # 850/mo
    assert _amount(_rule("active_mgmt_marketing"), DriverContext()) == Decimal("9900")  # 825/mo
    assert _amount(_rule("call_center"), DriverContext()) == Decimal("9000")  # 750/mo


def test_fixed_annual_used_as_is() -> None:
    assert _amount(_rule("ppc"), DriverContext()) == Decimal("12000")  # 12,000/yr (not ×12)


# ── PER_EMPLOYEE_MONTH — payroll budget allocation ──────────────────────────


def test_payroll_budget_85_per_employee_month() -> None:
    ctx = DriverContext(headcount=6)
    # 85 × 6 × 12 = 6,120, posted to its own GL (separate from actual wages 600140).
    out = compute_default(_rule("payroll_budget"), ctx)
    assert isinstance(out, DefaultComputation)
    assert out.annual_amount == Decimal("6120")
    assert out.target_account_code == "600145"


def test_payroll_budget_needs_headcount() -> None:
    assert isinstance(compute_default(_rule("payroll_budget"), DriverContext()), NeedsInput)


# ── Library integrity ───────────────────────────────────────────────────────


def test_rule_library_keys_unique_and_complete() -> None:
    keys = [r.rule_key for r in RULE_LIBRARY]
    assert len(keys) == len(set(keys))
    expected = {
        "insurance_pct",
        "cc_processing_pct",
        "utilities_pct",
        "utility_billback",
        "repairs_maintenance",
        "property_tax_uplift",
        "shield",
        "ppc",
        "seo_marketing",
        "active_mgmt_marketing",
        "call_center",
        "payroll_budget",
    }
    assert set(keys) == expected


def test_disabled_rule_returns_none() -> None:
    spec = RuleSpec("x", "X", RuleType.FIXED, Decimal("100"), "600410", enabled=False)
    assert compute_default(spec, DriverContext()) is None

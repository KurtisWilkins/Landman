"""Global default-rules config schemas (defaults engine, Part 2b) — the admin rule library."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class DefaultRuleRow(BaseModel):
    """One rule in the editable library."""

    rule_key: str
    label: str
    rule_type: str  # percent_of_gross_revenue | percent_of_line | per_unit_annual | …
    value: Decimal  # rate / per-unit $ / multiplier / fixed $
    target_account_code: str
    basis: str  # annual | monthly (FIXED rules)
    is_income_offset: bool
    overrides_actuals: bool
    driver_account_code: str | None = None
    soft_min: Decimal | None = None
    soft_max: Decimal | None = None
    must_fix: bool
    enabled: bool


class DefaultRulesDoc(BaseModel):
    rules: list[DefaultRuleRow] = Field(default_factory=list)


class DefaultRulePatch(BaseModel):
    """Edit a rule's tunables (the type + target GL are structural and not editable here)."""

    value: Decimal | None = None
    enabled: bool | None = None
    basis: str | None = None
    soft_min: Decimal | None = None
    soft_max: Decimal | None = None
    overrides_actuals: bool | None = None

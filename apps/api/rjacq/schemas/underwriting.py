"""Underwriting schemas (§8.3 underwriting) + assumption-override request (§9)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from .common import ApiModel


class Assumption(ApiModel):
    key: str
    label: str | None = None
    baseline_value: Decimal | None = None
    shield_source: str | None = None
    override_value: Decimal | None = None
    is_overridden: bool = False
    overridden_by: str | None = None
    note: str | None = None


class Hurdle(ApiModel):
    metric: str
    default_threshold: Decimal | None = None
    acquisition_threshold: Decimal | None = None
    actual: Decimal | None = Field(default=None, alias="actual_value")
    passes: bool | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class WaterfallTier(ApiModel):
    tier: int
    irr_floor: Decimal | None = None
    irr_ceiling: Decimal | None = None
    lp_split: Decimal | None = None
    gp_split: Decimal | None = None


class ProformaYear(ApiModel):
    yr: int
    revenue: Decimal | None = None
    opex: Decimal | None = None
    noi: Decimal | None = None
    debt_service: Decimal | None = None
    capex: Decimal | None = None
    levered_cf: Decimal | None = None


class ProformaExit(BaseModel):
    year: int | None = None
    exit_cap: Decimal | None = None
    gross_value: Decimal | None = None
    net_proceeds: Decimal | None = None


class ProformaResults(BaseModel):
    years: list[ProformaYear] = Field(default_factory=list)
    exit: ProformaExit | None = None
    levered_irr: Decimal | None = None
    equity_multiple: Decimal | None = None
    equity_basis: Decimal | None = None


class UnderwritingDoc(BaseModel):
    assumptions: list[Assumption] = Field(default_factory=list)
    hurdles: list[Hurdle] = Field(default_factory=list)
    waterfall_tiers: list[WaterfallTier] = Field(default_factory=list)
    proforma_results: ProformaResults | None = None


class AssumptionOverride(BaseModel):
    """PATCH /acquisitions/{id}/assumptions — records author + note (provenance)."""

    key: str
    override_value: Decimal
    note: str | None = None

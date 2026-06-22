"""Underwriting schemas (§8.3 underwriting) + assumption-override request (§9)."""

from __future__ import annotations

from datetime import date
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


class WaterfallTiersUpdate(BaseModel):
    """PUT /acquisitions/{id}/waterfall-tiers — the per-acquisition promote tiers. ``hurdles[i]`` is
    the tier's IRR hurdle, ``promotes[i]`` the GP/RJourney promote share (LP = 1 − promote).
    Replaces all tiers for the acquisition; the promote then reads them instead of the defaults."""

    hurdles: list[Decimal] = Field(default_factory=list)
    promotes: list[Decimal] = Field(default_factory=list)


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


class ProformaMonth(ApiModel):
    """One month of the levered cash flow (month 1..hold_years×12)."""

    month: int
    revenue: Decimal | None = None
    opex: Decimal | None = None
    noi: Decimal | None = None
    debt_service: Decimal | None = None
    capex: Decimal | None = None
    levered_cf: Decimal | None = None

    model_config = {"from_attributes": True}


class ProformaMonthlyResults(BaseModel):
    """GET /acquisitions/{id}/proforma-monthly — the 60-month grid (empty until a pro forma is
    computed). Each 12-month block rolls up to the matching ProformaResults year."""

    months: list[ProformaMonth] = Field(default_factory=list)


class UnderwritingDoc(BaseModel):
    assumptions: list[Assumption] = Field(default_factory=list)
    hurdles: list[Hurdle] = Field(default_factory=list)
    waterfall_tiers: list[WaterfallTier] = Field(default_factory=list)
    proforma_results: ProformaResults | None = None


class ProformaInputs(ApiModel):
    """GET/PUT /acquisitions/{id}/proforma-inputs — the canonical per-acquisition assumptions the
    pro forma, 60-month cash flow, and promote waterfall all read from. All optional; the pro forma
    is computed once the required ones (revenue, opex, exit cap, LTV, rate, amort term, hold) plus a
    purchase price are present. Percentages are decimals; null canonical-store fields fall back
    (loan_amount → price × ltv; revenue/expense_growth → noi_growth; coinvest/fees → defaults)."""

    stabilized_revenue: Decimal | None = None
    stabilized_opex: Decimal | None = None
    noi_growth: Decimal | None = None
    exit_cap: Decimal | None = None
    ltv: Decimal | None = None
    loan_rate: Decimal | None = None
    amort_months: int | None = None
    io_years: int | None = None
    selling_cost_rate: Decimal | None = None
    capex_reserve_rate: Decimal | None = None
    hold_years: int | None = None
    loan_amount: Decimal | None = None
    revenue_growth: Decimal | None = None
    expense_growth: Decimal | None = None
    rjourney_coinvest_pct: Decimal | None = None
    acquisition_fee_pct: Decimal | None = None
    mgmt_fee_pct: Decimal | None = None
    start_date: date | None = None

    model_config = {"from_attributes": True}


class ProformaInputsOut(ProformaInputs):
    """Response shape for GET /proforma-inputs. A distinct (output-only) class so FastAPI emits
    one stable component name instead of splitting the shared model into -Input/-Output."""


class AcquisitionReturns(ApiModel):
    """Headline returns for an acquisition (computed from its persisted pro forma + the standard
    promote). All null until a pro forma is computed. Output-only — used in the detail header and
    the pipeline list for at-a-glance comparison."""

    going_in_cap: Decimal | None = None
    loan_amount: Decimal | None = None
    ltv: Decimal | None = None
    hold_years: int | None = None
    equity: Decimal | None = None
    promote_value: Decimal | None = None
    partner_irr: Decimal | None = None
    partner_moic: Decimal | None = None
    rjourney_irr: Decimal | None = None
    rjourney_moic: Decimal | None = None
    deal_irr: Decimal | None = None
    deal_moic: Decimal | None = None


class UnderwritingDefaults(ApiModel):
    """Global pro-forma defaults that seed each acquisition's inputs. PUT body (all optional); the
    GET response (UnderwritingDefaultsOut) returns effective values (built-ins fill any nulls)."""

    ltv: Decimal | None = None
    loan_rate: Decimal | None = None
    noi_growth: Decimal | None = None
    exit_cap: Decimal | None = None
    selling_cost_rate: Decimal | None = None
    capex_reserve_rate: Decimal | None = None
    amort_months: int | None = None
    io_years: int | None = None
    hold_years: int | None = None
    rjourney_coinvest_pct: Decimal | None = None
    acquisition_fee_pct: Decimal | None = None
    mgmt_fee_pct: Decimal | None = None

    model_config = {"from_attributes": True}


class UnderwritingDefaultsOut(UnderwritingDefaults):
    """GET response — distinct (output-only) name avoids the -Input/-Output schema split."""


class AssumptionOverride(BaseModel):
    """PATCH /acquisitions/{id}/assumptions — records author + note (provenance)."""

    key: str
    override_value: Decimal
    note: str | None = None

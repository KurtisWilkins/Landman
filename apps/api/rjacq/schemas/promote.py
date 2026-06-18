"""Promote-waterfall calculator schemas (§9 surface, standalone tool).

Inputs default to the reference scenario so an empty POST returns it. Labels are genericized:
**Partner Equity** / **RJourney Equity** / **Combined Equity** — no fund/brand/property names.
Percentages are decimals (0.10 = 10%); money is Decimal.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from .common import ApiModel


class ExitAssumptionsIn(BaseModel):
    cap_rate: Decimal = Field(default=Decimal("0.05"), gt=0, le=1)
    base_value: Decimal = Field(default=Decimal("300000000"), ge=0)
    income_yield: Decimal = Field(default=Decimal("0.07"), ge=0, le=1)


class PromoteRequest(BaseModel):
    deal_name: str = "Deal 1"
    start_date: date = date(2025, 12, 31)
    hold_years: int = Field(default=5, ge=2, le=10)
    equity: Decimal = Field(default=Decimal("150000000"), gt=0)
    ltv: Decimal = Field(default=Decimal("0.65"), ge=0, lt=1)
    acquisition_fee_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    mgmt_fee_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    rjourney_coinvest_pct: Decimal = Field(default=Decimal("0.10"), ge=0, le=1)
    yr1_distribution_pct: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    distribution_growth: Decimal = Field(default=Decimal("0.05"), ge=-1, le=1)
    exit: ExitAssumptionsIn = Field(default_factory=ExitAssumptionsIn)
    hurdles: list[Decimal] = Field(
        default=[Decimal("0.08"), Decimal("0.15"), Decimal("0.20"), Decimal("0.20")],
    )
    promotes: list[Decimal] = Field(
        default=[Decimal("0.10"), Decimal("0.20"), Decimal("0.30"), Decimal("0.30")],
    )
    # When set, bypasses the generator and uses these deal-level cash flows directly.
    cashflow_override: list[Decimal] | None = None

    @model_validator(mode="after")
    def _validate(self) -> PromoteRequest:
        if len(self.hurdles) != 4 or len(self.promotes) != 4:
            raise ValueError("hurdles and promotes must each have 4 entries")
        if any(not (0 <= p <= 1) for p in self.promotes):
            raise ValueError("promote splits must be between 0 and 1")
        if any(h < 0 for h in self.hurdles):
            raise ValueError("hurdle rates must be non-negative")
        if self.cashflow_override is not None and len(self.cashflow_override) != (
            self.hold_years + 1
        ):
            raise ValueError("cashflow_override must have hold_years + 1 entries")
        return self


class TierOut(ApiModel):
    tier: int
    hurdle_rate: Decimal
    promote_pct: Decimal
    equity_total: Decimal
    carry_total: Decimal
    irr_check: Decimal | None
    binds: bool


class PositionOut(ApiModel):
    label: str
    cashflows: list[Decimal]
    equity: Decimal
    profit: Decimal
    irr: Decimal | None
    moic: Decimal | None


class PromoteResponse(ApiModel):
    deal_name: str
    dates: list[date]
    purchase_price: Decimal
    acquisition_fee: Decimal
    deal_cashflows: list[Decimal]
    combined_equity_distributions: list[Decimal]
    rjourney_carried_interest: list[Decimal]
    total_promote: Decimal
    tiers: list[TierOut]
    deal: PositionOut
    partner: PositionOut
    rjourney: PositionOut
    cashflow_ties_out: bool

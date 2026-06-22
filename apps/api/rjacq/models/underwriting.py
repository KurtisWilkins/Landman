"""Underwriting tables (§8.4 — Underwriting).

Assumptions record SHIELD baseline + override + author + note (provenance). Hurdle
thresholds and waterfall splits are per-acquisition data; their *defaults* are config, never
literals baked into code ([DECISION] A-1/A-2).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Assumption(Base):
    __tablename__ = "assumptions"

    assumption_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False
    )
    key: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str | None] = mapped_column(String)
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric)
    shield_source: Mapped[str | None] = mapped_column(String)
    override_value: Mapped[Decimal | None] = mapped_column(Numeric)
    is_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    overridden_by: Mapped[str | None] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(Text)


class Hurdle(Base):
    __tablename__ = "hurdles"

    hurdle_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String, nullable=False)
    default_threshold: Mapped[Decimal | None] = mapped_column(Numeric)
    acquisition_threshold: Mapped[Decimal | None] = mapped_column(Numeric)
    actual_value: Mapped[Decimal | None] = mapped_column(Numeric)
    passes: Mapped[bool | None] = mapped_column(Boolean)


class WaterfallTier(Base):
    __tablename__ = "waterfall_tiers"

    tier_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False
    )
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    irr_floor: Mapped[Decimal | None] = mapped_column(Numeric)
    irr_ceiling: Mapped[Decimal | None] = mapped_column(Numeric)  # null = top tier
    lp_split: Mapped[Decimal | None] = mapped_column(Numeric)
    gp_split: Mapped[Decimal | None] = mapped_column(Numeric)


class ProformaInput(Base):
    """Per-acquisition pro-forma assumptions the underwriter owns (debt terms, growth, exit,
    stabilized year-1 revenue/opex). One row per acquisition; the pro forma is recomputed from
    these + the acquisition's purchase price. Defaults are config/UI-seeded, never literals."""

    __tablename__ = "proforma_inputs"

    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), primary_key=True
    )
    stabilized_revenue: Mapped[Decimal | None] = mapped_column(Numeric)
    stabilized_opex: Mapped[Decimal | None] = mapped_column(Numeric)
    noi_growth: Mapped[Decimal | None] = mapped_column(Numeric)
    exit_cap: Mapped[Decimal | None] = mapped_column(Numeric)
    ltv: Mapped[Decimal | None] = mapped_column(Numeric)
    loan_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    amort_months: Mapped[int | None] = mapped_column(Integer)
    io_years: Mapped[int | None] = mapped_column(Integer)
    selling_cost_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    capex_reserve_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    hold_years: Mapped[int | None] = mapped_column(Integer)
    # Canonical-store additions. All nullable; a null falls back to today's behavior so every
    # existing acquisition computes identically until a value is set (one write, many reads).
    loan_amount: Mapped[Decimal | None] = mapped_column(Numeric)  # null → purchase_price × ltv
    revenue_growth: Mapped[Decimal | None] = mapped_column(Numeric)  # null → noi_growth
    expense_growth: Mapped[Decimal | None] = mapped_column(Numeric)  # null → noi_growth
    rjourney_coinvest_pct: Mapped[Decimal | None] = mapped_column(Numeric)  # GP equity share
    acquisition_fee_pct: Mapped[Decimal | None] = mapped_column(Numeric)
    mgmt_fee_pct: Mapped[Decimal | None] = mapped_column(Numeric)
    start_date: Mapped[date | None] = mapped_column(Date)  # drives the monthly series + XIRR


class ProformaResult(Base):
    __tablename__ = "proforma_results"

    result_id: Mapped[str] = mapped_column(String, primary_key=True)
    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), nullable=False
    )
    yr: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric)
    opex: Mapped[Decimal | None] = mapped_column(Numeric)
    noi: Mapped[Decimal | None] = mapped_column(Numeric)
    debt_service: Mapped[Decimal | None] = mapped_column(Numeric)
    capex: Mapped[Decimal | None] = mapped_column(Numeric)
    levered_cf: Mapped[Decimal | None] = mapped_column(Numeric)


class ProformaSummary(Base):
    __tablename__ = "proforma_summary"

    acquisition_id: Mapped[str] = mapped_column(
        ForeignKey("acquisitions.acquisition_id"), primary_key=True
    )
    levered_irr: Mapped[Decimal | None] = mapped_column(Numeric)
    equity_multiple: Mapped[Decimal | None] = mapped_column(Numeric)
    equity_basis: Mapped[Decimal | None] = mapped_column(Numeric)
    exit_year: Mapped[int | None] = mapped_column(Integer)
    exit_cap: Mapped[Decimal | None] = mapped_column(Numeric)
    exit_gross_value: Mapped[Decimal | None] = mapped_column(Numeric)
    exit_net_proceeds: Mapped[Decimal | None] = mapped_column(Numeric)


class UnderwritingDefaults(Base):
    """Singleton (id='default') of admin-set pro-forma defaults that seed each acquisition's
    inputs. A null column falls back to the built-in best-guess (underwriting/defaults.py)."""

    __tablename__ = "underwriting_defaults"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="default")
    ltv: Mapped[Decimal | None] = mapped_column(Numeric)
    loan_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    noi_growth: Mapped[Decimal | None] = mapped_column(Numeric)
    exit_cap: Mapped[Decimal | None] = mapped_column(Numeric)
    selling_cost_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    capex_reserve_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    amort_months: Mapped[int | None] = mapped_column(Integer)
    io_years: Mapped[int | None] = mapped_column(Integer)
    hold_years: Mapped[int | None] = mapped_column(Integer)
    # Org-wide JV terms that seed a new acquisition's promote inputs (null → built-in best-guess).
    rjourney_coinvest_pct: Mapped[Decimal | None] = mapped_column(Numeric)
    acquisition_fee_pct: Mapped[Decimal | None] = mapped_column(Numeric)
    mgmt_fee_pct: Mapped[Decimal | None] = mapped_column(Numeric)

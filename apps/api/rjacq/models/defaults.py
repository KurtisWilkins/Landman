"""Global budget-defaults rule config (defaults engine, Part 2b).

The admin-editable overlay over the code `RULE_LIBRARY` seed. One row per rule, **global** (not
per-acquisition): editing a rate/amount here changes the default everywhere it isn't manually
overridden on a deal. Seeded from `RULE_LIBRARY` (the sanctioned reset values); per CLAUDE.md the
numbers live in this config layer, never baked into the compute logic.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, updated_at_column


class DefaultRuleConfig(Base):
    """Persisted form of a `RuleSpec` — the live, editable rule library."""

    __tablename__ = "default_rules"

    rule_key: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)  # rate / $ / multiplier
    target_account_code: Mapped[str] = mapped_column(String, nullable=False)
    basis: Mapped[str] = mapped_column(String, nullable=False, default="annual")
    is_income_offset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    overrides_actuals: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    driver_account_code: Mapped[str | None] = mapped_column(String)
    soft_min: Mapped[Decimal | None] = mapped_column(Numeric)
    soft_max: Mapped[Decimal | None] = mapped_column(Numeric)
    must_fix: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = updated_at_column()
    updated_by: Mapped[str | None] = mapped_column(String)

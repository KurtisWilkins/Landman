"""widen proforma_inputs + underwriting_defaults for the canonical assumptions store

Additive nullable columns only — no data touched, no backfill. Every existing row keeps NULL and
the engine falls back to today's behavior (loan_amount → purchase_price × ltv; revenue_growth /
expense_growth → noi_growth; rjourney_coinvest_pct → config 0.10; fees → 0). Promote hurdles /
promote splits persist in the EXISTING waterfall_tiers table — no new table. See design doc §8.4.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Per-acquisition canonical inputs (single source of truth).
    for name in (
        "loan_amount",
        "revenue_growth",
        "expense_growth",
        "rjourney_coinvest_pct",
        "acquisition_fee_pct",
        "mgmt_fee_pct",
    ):
        op.add_column("proforma_inputs", sa.Column(name, sa.Numeric(), nullable=True))
    op.add_column("proforma_inputs", sa.Column("start_date", sa.Date(), nullable=True))

    # Global seed defaults for the org-wide JV terms (pre-fill a new acquisition's inputs).
    for name in ("rjourney_coinvest_pct", "acquisition_fee_pct", "mgmt_fee_pct"):
        op.add_column("underwriting_defaults", sa.Column(name, sa.Numeric(), nullable=True))


def downgrade() -> None:
    for name in ("mgmt_fee_pct", "acquisition_fee_pct", "rjourney_coinvest_pct"):
        op.drop_column("underwriting_defaults", name)
    for name in (
        "start_date",
        "mgmt_fee_pct",
        "acquisition_fee_pct",
        "rjourney_coinvest_pct",
        "expense_growth",
        "revenue_growth",
        "loan_amount",
    ):
        op.drop_column("proforma_inputs", name)

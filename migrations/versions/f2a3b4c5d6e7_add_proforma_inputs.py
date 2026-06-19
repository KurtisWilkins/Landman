"""add proforma_inputs (per-acquisition pro-forma assumptions)

Additive table only — one nullable row per acquisition. No data touched.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proforma_inputs",
        sa.Column("acquisition_id", sa.String(), nullable=False),
        sa.Column("stabilized_revenue", sa.Numeric(), nullable=True),
        sa.Column("stabilized_opex", sa.Numeric(), nullable=True),
        sa.Column("noi_growth", sa.Numeric(), nullable=True),
        sa.Column("exit_cap", sa.Numeric(), nullable=True),
        sa.Column("ltv", sa.Numeric(), nullable=True),
        sa.Column("loan_rate", sa.Numeric(), nullable=True),
        sa.Column("amort_months", sa.Integer(), nullable=True),
        sa.Column("io_years", sa.Integer(), nullable=True),
        sa.Column("selling_cost_rate", sa.Numeric(), nullable=True),
        sa.Column("capex_reserve_rate", sa.Numeric(), nullable=True),
        sa.Column("hold_years", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["acquisition_id"], ["acquisitions.acquisition_id"]),
        sa.PrimaryKeyConstraint("acquisition_id"),
    )


def downgrade() -> None:
    op.drop_table("proforma_inputs")

"""add proforma_monthly (60-month derived cash-flow grid)

Additive table only — a derived output cache (one row per month), replaced on each recompute like
proforma_results. No existing data touched. See design doc §8.4.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proforma_monthly",
        sa.Column("monthly_id", sa.String(), nullable=False),
        sa.Column("acquisition_id", sa.String(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Numeric(), nullable=True),
        sa.Column("opex", sa.Numeric(), nullable=True),
        sa.Column("noi", sa.Numeric(), nullable=True),
        sa.Column("debt_service", sa.Numeric(), nullable=True),
        sa.Column("capex", sa.Numeric(), nullable=True),
        sa.Column("levered_cf", sa.Numeric(), nullable=True),
        sa.ForeignKeyConstraint(["acquisition_id"], ["acquisitions.acquisition_id"]),
        sa.PrimaryKeyConstraint("monthly_id"),
    )


def downgrade() -> None:
    op.drop_table("proforma_monthly")

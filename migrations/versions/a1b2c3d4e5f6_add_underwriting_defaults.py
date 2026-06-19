"""add underwriting_defaults (singleton admin-set pro-forma defaults)

Additive singleton table — one row (id='default'). No data touched.

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-06-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "underwriting_defaults",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("ltv", sa.Numeric(), nullable=True),
        sa.Column("loan_rate", sa.Numeric(), nullable=True),
        sa.Column("noi_growth", sa.Numeric(), nullable=True),
        sa.Column("exit_cap", sa.Numeric(), nullable=True),
        sa.Column("selling_cost_rate", sa.Numeric(), nullable=True),
        sa.Column("capex_reserve_rate", sa.Numeric(), nullable=True),
        sa.Column("amort_months", sa.Integer(), nullable=True),
        sa.Column("io_years", sa.Integer(), nullable=True),
        sa.Column("hold_years", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("underwriting_defaults")

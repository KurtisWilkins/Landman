"""labor plan: per-deal positions

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-24

The Labor tab's positions. Each rolls up (via the pure labor engine) into the budget's Wages
cluster + work-camper revenue/credit lines. New table; additive.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "labor_positions",
        sa.Column("position_id", sa.String(), primary_key=True),
        sa.Column(
            "acquisition_id",
            sa.String(),
            sa.ForeignKey("acquisitions.acquisition_id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("employment_type", sa.String(), nullable=False),
        sa.Column("season", sa.String(), nullable=False),
        sa.Column("headcount", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("hours_per_week", sa.Numeric(), nullable=True),
        sa.Column("hourly_rate", sa.Numeric(), nullable=True),
        sa.Column("is_work_camper", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("benefits_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("site_weekly_rate", sa.Numeric(), nullable=True),
        sa.Column("campsite_credit_weekly", sa.Numeric(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("labor_positions")

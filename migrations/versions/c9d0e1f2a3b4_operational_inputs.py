"""operational inputs: per-deal driver capture (defaults engine, Part 1)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-29

Two new tables — ``operational_inputs`` (1:1 headcount + electric) and ``unit_groups`` (1:many
billable unit mix) — that feed the defaults engine's per-unit / per-employee / bill-back drivers.
Additive; both tables are new, nullable where a value may be "needs input".
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operational_inputs",
        sa.Column(
            "acquisition_id",
            sa.String(),
            sa.ForeignKey("acquisitions.acquisition_id"),
            primary_key=True,
        ),
        sa.Column("employee_headcount", sa.Integer(), nullable=True),
        sa.Column(
            "headcount_source", sa.String(), nullable=False, server_default="needs_input"
        ),
        sa.Column("electric_annual", sa.Numeric(), nullable=True),
        sa.Column(
            "electric_source", sa.String(), nullable=False, server_default="needs_input"
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "unit_groups",
        sa.Column("unit_group_id", sa.String(), primary_key=True),
        sa.Column(
            "acquisition_id",
            sa.String(),
            sa.ForeignKey("acquisitions.acquisition_id"),
            nullable=False,
        ),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("count", sa.Integer(), nullable=True),
        sa.Column("billable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(), nullable=False, server_default="needs_input"),
        sa.Column("sort", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_unit_groups_acquisition", "unit_groups", ["acquisition_id"])


def downgrade() -> None:
    op.drop_index("ix_unit_groups_acquisition", table_name="unit_groups")
    op.drop_table("unit_groups")
    op.drop_table("operational_inputs")

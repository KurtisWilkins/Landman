"""default rules: global admin-editable rule config (defaults engine, Part 2b)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-29

The global, admin-editable overlay over the code RULE_LIBRARY seed. One row per rule; seeded
(upsert) by the reference-data seed loader. Additive; new table only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "default_rules",
        sa.Column("rule_key", sa.String(), primary_key=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("rule_type", sa.String(), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("target_account_code", sa.String(), nullable=False),
        sa.Column("basis", sa.String(), nullable=False, server_default="annual"),
        sa.Column("is_income_offset", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("overrides_actuals", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("driver_account_code", sa.String(), nullable=True),
        sa.Column("soft_min", sa.Numeric(), nullable=True),
        sa.Column("soft_max", sa.Numeric(), nullable=True),
        sa.Column("must_fix", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("default_rules")

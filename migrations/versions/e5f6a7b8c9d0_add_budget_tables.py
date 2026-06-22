"""add budgets + budget_lines (year-one underwriting budget)

Additive tables only. budget_lines stores just the editable year-one cells (one per
acquisition/account/month); prior-year is computed on read from the mapped financial lines.
No existing data touched. See design doc §5.5 / §8.4.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("budget_id", sa.String(), nullable=False),
        sa.Column("acquisition_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_period_id", sa.String(), nullable=True),
        sa.Column("locked_by", sa.String(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["acquisition_id"], ["acquisitions.acquisition_id"]),
        sa.ForeignKeyConstraint(["source_period_id"], ["financial_periods.period_id"]),
        sa.PrimaryKeyConstraint("budget_id"),
        sa.UniqueConstraint("acquisition_id", name="uq_budget_acquisition"),
    )
    op.create_table(
        "budget_lines",
        sa.Column("budget_line_id", sa.String(), nullable=False),
        sa.Column("acquisition_id", sa.String(), nullable=False),
        sa.Column("account_code", sa.String(), nullable=False),
        sa.Column("month_index", sa.Integer(), nullable=False),
        sa.Column("year1_amount", sa.Numeric(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("default_rule_key", sa.String(), nullable=True),
        sa.Column("is_overridden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("overridden_by", sa.String(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("noi_placement", sa.String(), nullable=True),
        sa.Column("growth", sa.Numeric(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["acquisition_id"], ["acquisitions.acquisition_id"]),
        sa.ForeignKeyConstraint(["account_code"], ["gl_accounts.account_code"]),
        sa.PrimaryKeyConstraint("budget_line_id"),
        sa.UniqueConstraint("acquisition_id", "account_code", "month_index", name="uq_budget_cell"),
    )


def downgrade() -> None:
    op.drop_table("budget_lines")
    op.drop_table("budgets")

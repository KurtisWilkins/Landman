"""budget grid: editable prior + custom lines (two-column annual grid)

Revision ID: f3a4b5c6d7e8
Revises: e5f6a7b8c9d0
Create Date: 2026-06-24

Adds the columns the two-column underwriting grid needs: an editable ``prior_amount`` (override of
the mapped actual), free-text ``custom_label`` + ``section`` for non-GL line items,
``flagged_for_promotion`` (mark a custom line to add to the GL chart), and ``removed`` (drop a line
from the year-one projection while keeping its prior as reference). ``account_code`` becomes
nullable (custom lines have none). The grid is annual — collapse any pre-existing per-month rows
into one annual row (month_index = 0) per (acquisition, account); no-op on an empty table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f3a4b5c6d7e8"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("budget_lines", sa.Column("custom_label", sa.String(), nullable=True))
    op.add_column("budget_lines", sa.Column("section", sa.String(), nullable=True))
    op.add_column("budget_lines", sa.Column("prior_amount", sa.Numeric(), nullable=True))
    op.add_column(
        "budget_lines",
        sa.Column(
            "flagged_for_promotion", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.add_column(
        "budget_lines",
        sa.Column("removed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column(
        "budget_lines", "month_index", existing_type=sa.Integer(), server_default="0"
    )
    op.alter_column("budget_lines", "account_code", existing_type=sa.String(), nullable=True)

    # Collapse pre-existing per-month rows into one annual row per (acq, account): sum year1 onto
    # the lowest budget_line_id, mark it annual, then delete the rest. Guarded so it is a no-op on
    # an empty or already-annual table.
    op.execute(
        """
        WITH agg AS (
            SELECT acquisition_id, account_code,
                   SUM(COALESCE(year1_amount, 0)) AS total,
                   MIN(budget_line_id) AS keep_id,
                   bool_or(is_overridden) AS any_override
            FROM budget_lines
            WHERE account_code IS NOT NULL
            GROUP BY acquisition_id, account_code
            HAVING COUNT(*) > 1 OR MIN(month_index) <> 0
        )
        UPDATE budget_lines b
        SET year1_amount = agg.total, month_index = 0, is_overridden = agg.any_override
        FROM agg
        WHERE b.budget_line_id = agg.keep_id
        """
    )
    op.execute(
        """
        DELETE FROM budget_lines b
        USING (
            SELECT acquisition_id, account_code, MIN(budget_line_id) AS keep_id
            FROM budget_lines
            WHERE account_code IS NOT NULL
            GROUP BY acquisition_id, account_code
        ) agg
        WHERE b.acquisition_id = agg.acquisition_id
          AND b.account_code = agg.account_code
          AND b.budget_line_id <> agg.keep_id
        """
    )


def downgrade() -> None:
    op.alter_column("budget_lines", "account_code", existing_type=sa.String(), nullable=False)
    op.alter_column("budget_lines", "month_index", existing_type=sa.Integer(), server_default=None)
    op.drop_column("budget_lines", "removed")
    op.drop_column("budget_lines", "flagged_for_promotion")
    op.drop_column("budget_lines", "prior_amount")
    op.drop_column("budget_lines", "section")
    op.drop_column("budget_lines", "custom_label")

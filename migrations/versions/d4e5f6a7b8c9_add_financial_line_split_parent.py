"""add financial_lines.split_parent_id (1 seller line → many GLs)

Additive nullable self-FK. A split line keeps the original (parent) row as a non-counted
container (its account_code is set NULL, so the NOI bridge already skips it) and inserts one
child line per part, each pointing back via split_parent_id. No existing data touched.
See design doc §5.3.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "financial_lines",
        sa.Column("split_parent_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_financial_lines_split_parent",
        "financial_lines",
        "financial_lines",
        ["split_parent_id"],
        ["line_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_financial_lines_split_parent", "financial_lines", type_="foreignkey")
    op.drop_column("financial_lines", "split_parent_id")

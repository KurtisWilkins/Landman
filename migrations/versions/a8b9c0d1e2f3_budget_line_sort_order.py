"""budget lines: per-acquisition display order (drag-to-reorder)

Revision ID: a8b9c0d1e2f3
Revises: f4a5b6c7d8e9
Create Date: 2026-06-30

Adds ``budget_lines.sort_order`` so an operator can reorder line items within a section
(drag-and-drop). NULL = never moved → the grid falls back to the GL chart order. Additive and
nullable; presentational only (the NOI roll-up is section-based, order-independent).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("budget_lines", sa.Column("sort_order", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("budget_lines", "sort_order")

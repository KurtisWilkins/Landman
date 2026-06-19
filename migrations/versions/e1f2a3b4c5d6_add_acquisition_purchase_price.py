"""add acquisitions.purchase_price (negotiated price, distinct from OM ask_price)

Additive, nullable column — no backfill, no data touched.

Revision ID: e1f2a3b4c5d6
Revises: d9e8f7a6b5c4
Create Date: 2026-06-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d9e8f7a6b5c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("acquisitions", sa.Column("purchase_price", sa.Numeric(), nullable=True))


def downgrade() -> None:
    op.drop_column("acquisitions", "purchase_price")

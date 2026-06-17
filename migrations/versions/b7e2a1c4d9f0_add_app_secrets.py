"""add app_secrets (admin-managed encrypted integration keys)

Revision ID: b7e2a1c4d9f0
Revises: 6f81cfee1ece
Create Date: 2026-06-17 23:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2a1c4d9f0"
down_revision: str | None = "6f81cfee1ece"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_secrets",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("last4", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_secrets")

"""financial_period versioning (dated, retained upload versions)

Adds provenance + a current-version flag to ``financial_periods`` so a re-uploaded P&L becomes a
new dated version while prior versions are retained (append-never-overwrite). Additive only.

Revision ID: c3a5f2e8b1d4
Revises: b7e2a1c4d9f0
Create Date: 2026-06-18 00:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a5f2e8b1d4"
down_revision: str | None = "b7e2a1c4d9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("financial_periods", sa.Column("source_filename", sa.String(), nullable=True))
    op.add_column(
        "financial_periods",
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "financial_periods",
        sa.Column(
            "is_current",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("financial_periods", "is_current")
    op.drop_column("financial_periods", "ingested_at")
    op.drop_column("financial_periods", "source_filename")

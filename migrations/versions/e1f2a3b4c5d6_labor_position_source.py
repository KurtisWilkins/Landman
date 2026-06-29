"""labor positions: provenance source (OM seeding)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-29

Adds ``labor_positions.source`` (om | default | manual) so the staffing roster carries provenance
like the budget/operating fields. Additive; defaults existing rows to 'manual'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "labor_positions",
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
    )


def downgrade() -> None:
    op.drop_column("labor_positions", "source")

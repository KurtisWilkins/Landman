"""acquisition archive (soft-delete): archived_at + archived_by

Revision ID: a7b8c9d0e1f2
Revises: f3a4b5c6d7e8
Create Date: 2026-06-24

Archiving moves a deal out of the active pipeline without deleting it (recoverable via restore).
``archived_at`` NULL = active; ``status`` (active/failed/…) is orthogonal and preserved. Additive
and nullable — safe expand-contract.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("acquisitions", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("acquisitions", sa.Column("archived_by", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("acquisitions", "archived_by")
    op.drop_column("acquisitions", "archived_at")

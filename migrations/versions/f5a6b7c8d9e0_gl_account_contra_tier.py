"""gl_accounts: contra flag + core/rare tier (canonical chart metadata)

Revision ID: f5a6b7c8d9e0
Revises: a8b9c0d1e2f3
Create Date: 2026-06-30

Adds two additive, nullable-safe columns to ``gl_accounts`` so the canonical chart of accounts
(derived from the RJourney consolidated income statement) can carry the metadata the Budget tab
and OM-mapping need:

- ``is_contra`` — the line is a sign-preserving negative offset that nets against its siblings
  (e.g. 605415 Utility Recovery, 421000 Discounts). Defaults to false.
- ``tier`` — "core" (in most parks) vs "rare" (long-tail) for leaves; NULL for group headers.
  Drives the optional "hide rare lines" toggle.

Both are additive; the seed backfills them. Presentational/roll-up metadata only — no data loss.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gl_accounts",
        sa.Column("is_contra", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("gl_accounts", sa.Column("tier", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("gl_accounts", "tier")
    op.drop_column("gl_accounts", "is_contra")

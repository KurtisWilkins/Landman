"""rename deal -> acquisition (tables, deal_id columns, deal_status enum)

Data-preserving rename only — RENAME TABLE / RENAME COLUMN / ALTER TYPE ... RENAME.
No data is dropped or rewritten, so existing acquisitions and their children survive.
Internal constraint/index names (e.g. ``*_deal_id_fkey``, ``deals_pkey``) are left as-is:
Postgres keeps them through a rename and the ORM never references them by name; renaming
them would add risk for no runtime benefit.

Revision ID: d9e8f7a6b5c4
Revises: c3a5f2e8b1d4
Create Date: 2026-06-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d9e8f7a6b5c4"
down_revision: str | None = "c3a5f2e8b1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every table that carries a deal_id column (post-table-rename names).
_DEAL_ID_TABLES = [
    "acquisitions",
    "amenities",
    "assumptions",
    "bookings",
    "comps",
    "acquisition_gate_items",
    "acquisition_photos",
    "feedback_items",
    "financial_periods",
    "hurdles",
    "proforma_results",
    "proforma_summary",
    "units",
    "waterfall_tiers",
    "weekly_summary",
    "financial_lines",
    "population_rings",  # added in migration 6f81cfee1ece (after the initial schema)
]


def upgrade() -> None:
    # Enum type rename first (the deals.status column references it).
    op.execute("ALTER TYPE deal_status RENAME TO acquisition_status")
    # Rename the three tables whose names embed "deal" (FKs follow automatically).
    op.rename_table("deals", "acquisitions")
    op.rename_table("deal_photos", "acquisition_photos")
    op.rename_table("deal_gate_items", "acquisition_gate_items")
    # Rename the deal_id column -> acquisition_id everywhere it appears.
    for table in _DEAL_ID_TABLES:
        op.alter_column(table, "deal_id", new_column_name="acquisition_id")
    # The one other "deal"-named column: hurdles.deal_threshold (per-acquisition override).
    op.alter_column("hurdles", "deal_threshold", new_column_name="acquisition_threshold")


def downgrade() -> None:
    op.alter_column("hurdles", "acquisition_threshold", new_column_name="deal_threshold")
    for table in _DEAL_ID_TABLES:
        op.alter_column(table, "acquisition_id", new_column_name="deal_id")
    op.rename_table("acquisition_gate_items", "deal_gate_items")
    op.rename_table("acquisition_photos", "deal_photos")
    op.rename_table("acquisitions", "deals")
    op.execute("ALTER TYPE acquisition_status RENAME TO deal_status")

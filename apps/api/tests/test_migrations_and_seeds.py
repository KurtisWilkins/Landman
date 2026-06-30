"""Real-Postgres tests: the §8 migration applies and reference seeds load correctly."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import create_engine


def _sync_engine(url: str):
    return create_engine(url.replace("+asyncpg", "+psycopg"), future=True)


def test_full_schema_present(migrated_db: str) -> None:
    """All 23 §8 tables exist after ``alembic upgrade head``."""
    expected = {
        "acquisitions",
        "acquisition_photos",
        "gl_accounts",
        "gl_mappings_learned",
        "gate_questions",
        "financial_periods",
        "financial_lines",
        "units",
        "amenities",
        "bookings",
        "weekly_summary",
        "assumptions",
        "hurdles",
        "waterfall_tiers",
        "proforma_results",
        "proforma_summary",
        "comps",
        "acquisition_gate_items",
        "question_suggestions",
        "feedback_items",
        "feedback_attachments",
        "feedback_comments",
        "feedback_dispatch",
    }
    eng = _sync_engine(migrated_db)
    with eng.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        ).scalars()
        present = set(rows)
    assert expected <= present


def test_pgvector_extension_and_embedding_column(migrated_db: str) -> None:
    eng = _sync_engine(migrated_db)
    with eng.connect() as conn:
        ext = conn.execute(sa.text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar()
        assert ext == 1
        coltype = conn.execute(
            sa.text(
                "SELECT udt_name FROM information_schema.columns "
                "WHERE table_name='gl_accounts' AND column_name='embedding'"
            )
        ).scalar()
        assert coltype == "vector"


def test_unmapped_financial_line_account_code_nullable(migrated_db: str) -> None:
    """financial_lines.account_code is nullable on purpose (unmapped lines persist)."""
    eng = _sync_engine(migrated_db)
    with eng.connect() as conn:
        nullable = conn.execute(
            sa.text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name='financial_lines' AND column_name='account_code'"
            )
        ).scalar()
    assert nullable == "YES"


def test_seeds_load_gl_and_gates(migrated_db: str) -> None:
    import asyncio

    from rjacq.seeds.load import run

    asyncio.run(run())  # idempotent
    eng = _sync_engine(migrated_db)
    with eng.connect() as conn:
        gl = conn.execute(sa.text("SELECT count(*) FROM gl_accounts")).scalar()
        gates = conn.execute(sa.text("SELECT count(*) FROM gate_questions")).scalar()
        # Below-the-line accounts carry their NOI placement defaults (§8.5).
        debt = conn.execute(
            sa.text("SELECT default_noi_placement FROM gl_accounts WHERE account_code='700000'")
        ).scalar()
        nonop = conn.execute(
            sa.text("SELECT default_noi_placement FROM gl_accounts WHERE account_code='800000'")
        ).scalar()
    assert gl >= 20
    assert gates >= 4
    assert debt == "below"
    assert nonop == "non_operating"


def test_gl_hierarchy_parent_links(migrated_db: str) -> None:
    """Leaf 400105 rolls up to subgroup 400100 rolls up to major_group 400000."""
    import asyncio

    from rjacq.seeds.load import run

    asyncio.run(run())  # seed the chart here — don't rely on a sibling test's data (idempotent)
    eng = _sync_engine(migrated_db)
    with eng.connect() as conn:
        parent_of_leaf = conn.execute(
            sa.text("SELECT parent_code FROM gl_accounts WHERE account_code='400105'")
        ).scalar()
        parent_of_subgroup = conn.execute(
            sa.text("SELECT parent_code FROM gl_accounts WHERE account_code='400100'")
        ).scalar()
    assert parent_of_leaf == "400100"
    assert parent_of_subgroup == "400000"

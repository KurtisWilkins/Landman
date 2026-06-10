"""Test fixtures.

Repository/DB tests run against a **real** Postgres (CLAUDE.md): either ``TEST_DATABASE_URL``
if set (used in CI and locally), or an ephemeral ``pgvector`` testcontainer. If neither a URL
nor Docker is available, DB-backed tests are skipped (pure-contract tests still run).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def db_url() -> Iterator[str]:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield url
        return
    try:
        from testcontainers.postgres import PostgresContainer
    except Exception:  # pragma: no cover - optional dep
        pytest.skip("no TEST_DATABASE_URL and testcontainers unavailable")
    try:
        with PostgresContainer("pgvector/pgvector:pg16", driver="psycopg") as pg:
            yield pg.get_connection_url()
    except Exception as exc:  # pragma: no cover - docker unavailable
        pytest.skip(f"could not start Postgres testcontainer: {exc}")


@pytest.fixture(scope="session")
def migrated_db(db_url: str) -> str:
    """Apply Alembic migrations to a fresh database, return its URL."""
    import pathlib

    from alembic import command
    from alembic.config import Config

    os.environ["DATABASE_URL"] = db_url
    # Settings is cached; refresh so the engine/migrations use the test URL.
    from rjacq.core import config as cfg

    cfg.get_settings.cache_clear()
    cfg.settings = cfg.get_settings()

    # core.db binds its engine/session factory at import time from the (default) settings.
    # Tests switch the URL afterwards, and import order determines whether code paths that
    # use core.db (endpoints via get_session, the seed loader) saw the default or the test
    # URL. Rebind here so they always target the test DB regardless of import order.
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from rjacq.core import db as core_db

    core_db.engine = create_async_engine(
        cfg.settings.async_database_url, pool_pre_ping=True, future=True
    )
    core_db.SessionFactory = async_sessionmaker(
        core_db.engine, expire_on_commit=False, class_=AsyncSession
    )

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    alembic_cfg = Config(str(repo_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(repo_root / "migrations"))
    command.upgrade(alembic_cfg, "head")
    return db_url


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient for contract/stub tests (no DB needed)."""
    from rjacq.main import create_app

    with TestClient(create_app()) as c:
        yield c

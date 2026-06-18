"""Admin integration-key management (ADR-0012): encrypted DB override + admin-only API.

Real Postgres via the shared migrated DB. Secrets are write-only — the API returns status only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi.testclient import TestClient
from rjacq.core import app_config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ADMIN = {"Authorization": "Bearer dev admin"}
ANALYST = {"Authorization": "Bearer dev analyst"}


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_effective_secret_db_override_then_env(session: AsyncSession, monkeypatch) -> None:
    # Patch the settings object app_config actually reads (robust to migrated_db swapping it).
    monkeypatch.setattr(app_config.settings, "anthropic_api_key", "env-key-0000")
    await app_config.clear_secret(session, "anthropic_api_key")  # clean state (DB persists)
    await session.commit()
    assert await app_config.effective_secret(session, "anthropic_api_key") == "env-key-0000"

    await app_config.set_secret(session, "anthropic_api_key", "db-key-9999", actor="boss@x.com")
    await session.commit()
    assert await app_config.effective_secret(session, "anthropic_api_key") == "db-key-9999"

    await app_config.clear_secret(session, "anthropic_api_key")
    await session.commit()
    assert await app_config.effective_secret(session, "anthropic_api_key") == "env-key-0000"


def test_list_requires_admin(migrated_db: str, client: TestClient) -> None:
    assert client.get("/admin/integrations", headers=ANALYST).status_code == 403


def test_set_masks_value_and_persists(migrated_db: str, client: TestClient) -> None:
    r = client.put(
        "/admin/integrations/anthropic_api_key",
        json={"value": "sk-ant-secret-ABCD"},
        headers=ADMIN,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is True
    assert body["source"] == "database"
    assert body["hint"] == "ABCD"  # last 4 only — the full value is never returned
    assert "value" not in body

    listed = client.get("/admin/integrations", headers=ADMIN).json()
    anth = next(i for i in listed if i["key"] == "anthropic_api_key")
    assert anth["configured"] and anth["source"] == "database" and anth["hint"] == "ABCD"


def test_unknown_key_404(migrated_db: str, client: TestClient) -> None:
    r = client.put("/admin/integrations/not_a_key", json={"value": "x"}, headers=ADMIN)
    assert r.status_code == 404


def test_blank_value_rejected(migrated_db: str, client: TestClient) -> None:
    r = client.put("/admin/integrations/voyage_api_key", json={"value": "   "}, headers=ADMIN)
    assert r.status_code == 400

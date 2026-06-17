"""Auth: production trusts the EasyAuth-forwarded principal only via the proxy secret (ADR-0011).

The protected stub ``GET /deals`` requires ``deal:read``; ADMIN holds it, so a fully trusted
admin request passes auth + RBAC and reaches the not-yet-implemented body (501 not_implemented).
Auth failures surface *before* that as 401/403/501-auth_not_configured.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from rjacq.core.config import settings

SECRET = "proxy-secret-xyz"
ADMIN = "boss@rossmgt.com"


@pytest.fixture
def prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "proxy_auth_secret", SECRET)
    monkeypatch.setattr(settings, "admin_emails", ADMIN)
    monkeypatch.setattr(settings, "executive_emails", "")
    monkeypatch.setattr(settings, "equity_partner_emails", "")
    monkeypatch.setattr(settings, "analyst_emails", "")


def _headers(secret: str | None, email: str | None) -> dict[str, str]:
    h: dict[str, str] = {}
    if secret is not None:
        h["X-Proxy-Auth"] = secret
    if email is not None:
        h["X-MS-CLIENT-PRINCIPAL-NAME"] = email
    return h


def test_trusted_admin_passes_auth_and_rbac(prod: None, client: TestClient) -> None:
    r = client.get("/deals", headers=_headers(SECRET, ADMIN))
    assert r.status_code == 501  # cleared auth + RBAC, reached the stub body
    assert r.json()["error"]["code"] == "not_implemented"


def test_email_match_is_case_insensitive(prod: None, client: TestClient) -> None:
    r = client.get("/deals", headers=_headers(SECRET, "Boss@RossMgt.com"))
    assert r.status_code == 501


def test_wrong_proxy_secret_is_unauthorized(prod: None, client: TestClient) -> None:
    r = client.get("/deals", headers=_headers("not-the-secret", ADMIN))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_missing_proxy_secret_is_unauthorized(prod: None, client: TestClient) -> None:
    r = client.get("/deals", headers=_headers(None, ADMIN))
    assert r.status_code == 401


def test_no_principal_is_unauthorized(prod: None, client: TestClient) -> None:
    r = client.get("/deals", headers=_headers(SECRET, None))
    assert r.status_code == 401


def test_unprovisioned_email_is_forbidden(prod: None, client: TestClient) -> None:
    r = client.get("/deals", headers=_headers(SECRET, "stranger@example.com"))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_secret_not_configured_returns_501_auth(
    prod: None, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "proxy_auth_secret", None)
    r = client.get("/deals", headers=_headers(SECRET, ADMIN))
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "auth_not_configured"


def test_production_ignores_dev_bearer(prod: None, client: TestClient) -> None:
    # The local dev shim must never grant access in production.
    r = client.get("/deals", headers={"Authorization": "Bearer dev admin"})
    assert r.status_code == 401


def test_local_dev_shim_still_works(client: TestClient) -> None:
    # Default app_env is local: the Bearer dev <role> shim resolves a principal.
    r = client.get("/deals", headers={"Authorization": "Bearer dev admin"})
    assert r.status_code == 501  # reached the stub via the dev principal

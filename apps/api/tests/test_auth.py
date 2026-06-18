"""Auth: production trusts the EasyAuth-forwarded principal only via the proxy secret (ADR-0011).

We probe with the still-stubbed ``PATCH /acquisitions/{id}/phase`` (requires ``phase:advance``,
which ADMIN holds): a fully trusted admin passes auth + RBAC and reaches the not-yet-implemented
body (501 not_implemented). Auth failures surface *before* that as 401/403/501-auth_not_configured.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

SECRET = "proxy-secret-xyz"
ADMIN = "boss@rossmgt.com"


def _set_settings(monkeypatch: pytest.MonkeyPatch, **values: object) -> None:
    """Set attrs on the live settings object(s).

    ``auth`` binds ``settings`` at import while ``rbac.role_for_email`` reads it lazily, and a
    DB test's ``migrated_db`` fixture may have swapped ``config.settings`` for a fresh instance.
    Patch every distinct settings object both modules currently reference so the override lands
    regardless of import/test order.
    """
    from rjacq.core import auth as auth_mod
    from rjacq.core import config as config_mod

    objs = {id(auth_mod.settings): auth_mod.settings, id(config_mod.settings): config_mod.settings}
    for obj in objs.values():
        for key, value in values.items():
            monkeypatch.setattr(obj, key, value)


@pytest.fixture
def prod(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_settings(
        monkeypatch,
        app_env="production",
        proxy_auth_secret=SECRET,
        admin_emails=ADMIN,
        executive_emails="",
        equity_partner_emails="",
        analyst_emails="",
    )


def _headers(secret: str | None, email: str | None) -> dict[str, str]:
    h: dict[str, str] = {}
    if secret is not None:
        h["X-Proxy-Auth"] = secret
    if email is not None:
        h["X-MS-CLIENT-PRINCIPAL-NAME"] = email
    return h


def test_trusted_admin_passes_auth_and_rbac(prod: None, client: TestClient) -> None:
    r = client.patch("/acquisitions/dl_x/phase", json={}, headers=_headers(SECRET, ADMIN))
    assert r.status_code == 501  # cleared auth + RBAC, reached the stub body
    assert r.json()["error"]["code"] == "not_implemented"


def test_email_match_is_case_insensitive(prod: None, client: TestClient) -> None:
    r = client.patch(
        "/acquisitions/dl_x/phase", json={}, headers=_headers(SECRET, "Boss@RossMgt.com")
    )
    assert r.status_code == 501


def test_wrong_proxy_secret_is_unauthorized(prod: None, client: TestClient) -> None:
    r = client.patch("/acquisitions/dl_x/phase", json={}, headers=_headers("not-the-secret", ADMIN))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_missing_proxy_secret_is_unauthorized(prod: None, client: TestClient) -> None:
    r = client.patch("/acquisitions/dl_x/phase", json={}, headers=_headers(None, ADMIN))
    assert r.status_code == 401


def test_no_principal_is_unauthorized(prod: None, client: TestClient) -> None:
    r = client.patch("/acquisitions/dl_x/phase", json={}, headers=_headers(SECRET, None))
    assert r.status_code == 401


def test_unprovisioned_email_is_forbidden(prod: None, client: TestClient) -> None:
    r = client.patch(
        "/acquisitions/dl_x/phase", json={}, headers=_headers(SECRET, "stranger@example.com")
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_secret_not_configured_returns_501_auth(
    prod: None, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_settings(monkeypatch, proxy_auth_secret=None)
    r = client.patch("/acquisitions/dl_x/phase", json={}, headers=_headers(SECRET, ADMIN))
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "auth_not_configured"


def test_production_ignores_dev_bearer(prod: None, client: TestClient) -> None:
    # The local dev shim must never grant access in production.
    r = client.patch(
        "/acquisitions/dl_x/phase", json={}, headers={"Authorization": "Bearer dev admin"}
    )
    assert r.status_code == 401


def test_local_dev_shim_still_works(client: TestClient) -> None:
    # Default app_env is local: the Bearer dev <role> shim resolves a principal.
    r = client.patch(
        "/acquisitions/dl_x/phase", json={}, headers={"Authorization": "Bearer dev admin"}
    )
    assert r.status_code == 501  # reached the stub via the dev principal

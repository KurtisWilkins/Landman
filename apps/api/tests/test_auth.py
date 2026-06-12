"""Easy Auth identity → Principal mapping (C-16 internal path, ADR-0011).

The Container Apps proxy injects ``X-MS-CLIENT-PRINCIPAL-NAME``; we authorize it against the
configured allowlists and deny anyone not listed. The proxy secret guards the internal API from
in-environment spoofing.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from rjacq.core import auth
from rjacq.core.config import settings
from rjacq.core.rbac import Role


async def _principal(**headers: str | None) -> auth.Principal:
    return await auth.get_current_principal(
        authorization=headers.get("authorization"),
        x_ms_client_principal_name=headers.get("name"),
        x_ms_client_principal_id=headers.get("id"),
        x_proxy_auth=headers.get("proxy"),
    )


def test_role_for_email_uses_allowlists(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "admin_emails", "Boss@RJourney.com")
    monkeypatch.setattr(settings, "analyst_emails", "staff@rjourney.com, two@rjourney.com")
    assert auth.role_for_email("boss@rjourney.com") is Role.ADMIN  # case-insensitive
    assert auth.role_for_email(" STAFF@rjourney.com ") is Role.ANALYST
    assert auth.role_for_email("stranger@example.com") is None  # not on any list → denied


@pytest.mark.asyncio
async def test_proxy_identity_maps_to_admin(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "admin_emails", "boss@rjourney.com")
    monkeypatch.setattr(settings, "proxy_auth_secret", None)
    p = await _principal(name="boss@rjourney.com", id="aad-123")
    assert p.role is Role.ADMIN
    assert p.email == "boss@rjourney.com"
    assert p.user_id == "aad-123"


@pytest.mark.asyncio
async def test_authenticated_but_unlisted_is_forbidden(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "admin_emails", "boss@rjourney.com")
    monkeypatch.setattr(settings, "analyst_emails", "")
    monkeypatch.setattr(settings, "proxy_auth_secret", None)
    with pytest.raises(HTTPException) as exc:
        await _principal(name="stranger@example.com")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_proxy_secret_required_when_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "admin_emails", "boss@rjourney.com")
    monkeypatch.setattr(settings, "proxy_auth_secret", "s3cr3t")
    # Identity without the shared secret (a direct in-environment call) is not trusted.
    with pytest.raises(HTTPException) as exc:
        await _principal(name="boss@rjourney.com", proxy="wrong")
    assert exc.value.status_code == 401
    # With the right secret it is honored.
    p = await _principal(name="boss@rjourney.com", proxy="s3cr3t")
    assert p.role is Role.ADMIN


@pytest.mark.asyncio
async def test_missing_credentials_is_unauthorized(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(HTTPException) as exc:
        await _principal()
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_bearer_shim_refused_in_production(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(HTTPException) as exc:
        await _principal(authorization="Bearer dev admin")
    assert exc.value.status_code == 501  # decode_token refuses to mint identity in prod

"""Authentication skeleton.

Two entry paths (design doc §2, §10), both unresolved pending [DECISION] C-16:
  • Internal users — Microsoft Entra ID (Azure AD) SSO via OIDC.
  • External PE partners — a secondary method (magic-link or password).

This module provides the seams (principal model, token decode hook, FastAPI dependency)
without committing to provider specifics. The real OIDC discovery/JWKS verification is
wired once C-16 is confirmed; until then ``decode_token`` is a guarded placeholder that
refuses to fabricate a trusted identity in production.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from .config import settings
from .rbac import Role, role_for_email


@dataclass(frozen=True)
class Principal:
    """An authenticated caller. RBAC decisions are made server-side from ``role``."""

    user_id: str
    email: str
    role: Role
    # For external PE partners, deal access is scoped — populated once D-24 is resolved.
    scoped_deal_ids: frozenset[str] | None = None


def _principal_from_proxy(proxy_auth: str | None, email: str | None) -> Principal:
    """Build a Principal from the identity forwarded by the EasyAuth edge (ADR-0011).

    The API has its own ingress, so the forwarded ``X-MS-CLIENT-PRINCIPAL-NAME`` is trusted
    ONLY when ``X-Proxy-Auth`` carries the shared secret that our nginx injects (and which a
    client cannot supply — nginx overwrites it). Constant-time compare avoids leaking the
    secret via timing.
    """
    expected = settings.proxy_auth_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "error": {
                    "code": "auth_not_configured",
                    "message": "Edge authentication is not yet configured (decision C-16).",
                }
            },
        )
    if not proxy_auth or not secrets.compare_digest(proxy_auth, expected):
        raise _unauthorized("request did not arrive through the authenticated proxy")
    if not email:
        raise _unauthorized("no authenticated principal")
    role = role_for_email(email)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "forbidden",
                    "message": "Your account is not provisioned for this application.",
                }
            },
        )
    return Principal(user_id=email.strip().lower(), email=email, role=role)


def decode_token(token: str) -> Principal:
    """Validate a bearer token and return the Principal.

    TODO(decision: §14 C-16): wire Entra OIDC (issuer/JWKS from config) for internal
    users and the external method for PE partners. Until then this only supports a local
    development shim and must never mint a trusted identity in production.
    """
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "error": {
                    "code": "auth_not_configured",
                    "message": "OIDC/external auth is not yet configured (decision C-16).",
                }
            },
        )
    # Local dev shim: "dev <role>" → a principal with that role. Never used in prod.
    if token.startswith("dev "):
        role_name = token.split(" ", 1)[1].strip()
        try:
            role = Role(role_name)
        except ValueError as exc:
            raise _unauthorized("unknown dev role") from exc
        return Principal(user_id=f"dev_{role.value}", email=f"{role.value}@local", role=role)
    raise _unauthorized("invalid token")


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "unauthorized", "message": message}},
    )


async def get_current_principal(
    authorization: str | None = Header(default=None),
    x_proxy_auth: str | None = Header(default=None),
    x_ms_client_principal_name: str | None = Header(default=None),
) -> Principal:
    """FastAPI dependency: resolve the caller into a Principal.

    Production trusts the identity forwarded by the EasyAuth edge (via the proxy secret);
    locally a ``Bearer dev <role>`` shim is used (never trusted in production).
    """
    if settings.is_production:
        return _principal_from_proxy(x_proxy_auth, x_ms_client_principal_name)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("missing bearer token")
    token = authorization.split(" ", 1)[1]
    return decode_token(token)


# Convenience dependency alias for routers.
CurrentPrincipal = Depends(get_current_principal)

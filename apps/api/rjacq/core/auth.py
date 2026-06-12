"""Authentication skeleton.

Two entry paths (design doc §2, §10), both unresolved pending [DECISION] C-16:
  • Internal users — Microsoft Entra ID (Azure AD) SSO via OIDC.
  • External PE partners — a secondary method (magic-link or password).

Internal users (C-16 internal path, ADR-0011): **Microsoft/Entra via Azure Container Apps
Easy Auth** — the platform verifies the token and injects the identity, which we read here and
authorize against an email allowlist (``role_for_email``). The bearer ``decode_token`` path is a
local-dev shim only and refuses to fabricate a trusted identity in production. The external
PE-partner method is still unresolved under C-16.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from .config import settings
from .rbac import Role


@dataclass(frozen=True)
class Principal:
    """An authenticated caller. RBAC decisions are made server-side from ``role``."""

    user_id: str
    email: str
    role: Role
    # For external PE partners, deal access is scoped — populated once D-24 is resolved.
    scoped_deal_ids: frozenset[str] | None = None


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


def _forbidden(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": {"code": "forbidden", "message": message}},
    )


def role_for_email(email: str) -> Role | None:
    """Map an authenticated email to a Role via the configured allowlists (C-16, ADR-0011).

    Returns ``None`` when the user is on no list — an authenticated-but-unauthorized caller is
    denied rather than granted a default role (CLAUDE.md: never loosen RBAC).
    """
    email = email.strip().lower()
    if email in settings.admin_email_set:
        return Role.ADMIN
    if email in settings.analyst_email_set:
        return Role.ANALYST
    return None


def principal_from_proxy_identity(email: str, user_id: str | None) -> Principal:
    """Build a Principal from the identity injected by Container Apps Easy Auth."""
    role = role_for_email(email)
    if role is None:
        raise _forbidden(f"{email.strip().lower()} is not authorized for this application")
    normalized = email.strip().lower()
    return Principal(user_id=user_id or normalized, email=normalized, role=role)


async def get_current_principal(
    authorization: str | None = Header(default=None),
    x_ms_client_principal_name: str | None = Header(default=None),
    x_ms_client_principal_id: str | None = Header(default=None),
    x_proxy_auth: str | None = Header(default=None),
) -> Principal:
    """FastAPI dependency: resolve the caller into a Principal.

    Primary (production): identity injected by the Container Apps Easy Auth web proxy. We trust
    the ``X-MS-CLIENT-PRINCIPAL-NAME`` header only when it arrives with the shared proxy secret,
    so an in-environment caller hitting the internal API directly cannot spoof an identity.
    Fallback: a bearer token (local-dev shim only; ``decode_token`` refuses to mint one in prod).
    """
    if x_ms_client_principal_name:
        if settings.proxy_auth_secret and x_proxy_auth != settings.proxy_auth_secret:
            raise _unauthorized("proxy identity is not trusted")
        return principal_from_proxy_identity(x_ms_client_principal_name, x_ms_client_principal_id)
    if authorization and authorization.lower().startswith("bearer "):
        return decode_token(authorization.split(" ", 1)[1])
    raise _unauthorized("missing credentials")


# Convenience dependency alias for routers.
CurrentPrincipal = Depends(get_current_principal)

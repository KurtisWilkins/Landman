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


async def get_current_principal(
    authorization: str | None = Header(default=None),
) -> Principal:
    """FastAPI dependency: extract + validate the bearer token into a Principal."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("missing bearer token")
    token = authorization.split(" ", 1)[1]
    return decode_token(token)


# Convenience dependency alias for routers.
CurrentPrincipal = Depends(get_current_principal)

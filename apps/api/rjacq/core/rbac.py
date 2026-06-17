"""Role-based access control (design doc §2). Enforced server-side on every endpoint.

Capability matrix is intentionally coarse for Phase 0; per-capability checks are added as
the relevant phases land. Per CLAUDE.md, never trust the client for role.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, status


class Role(str, enum.Enum):
    """The four §2 roles."""

    ADMIN = "admin"  # Kurtis — everything; approves gate changes; triages feedback
    EXECUTIVE = "executive"  # CEO — full read; advance/kill; comment
    EQUITY_PARTNER = "equity_partner"  # PE reviewers — scoped read; comment; answer
    ANALYST = "analyst"  # staff — upload, answer, suggest, submit feedback


# Coarse capabilities used by Phase-0 stubs; expanded per phase.
class Capability(str, enum.Enum):
    DEAL_READ = "deal:read"
    DEAL_WRITE = "deal:write"
    PHASE_ADVANCE = "phase:advance"  # advance/kill a deal (gated)
    ASSUMPTION_OVERRIDE = "assumption:override"
    GATE_APPROVE = "gate:approve"  # approve gate-question suggestions (admin only)
    FEEDBACK_SUBMIT = "feedback:submit"
    FEEDBACK_TRIAGE = "feedback:triage"  # triage + dispatch (admin; others per A-33)
    MAPPING_CONFIRM = "mapping:confirm"
    SETTINGS_MANAGE = "settings:manage"  # view/set integration keys (admin only)


_MATRIX: dict[Role, set[Capability]] = {
    Role.ADMIN: set(Capability),
    Role.EXECUTIVE: {
        Capability.DEAL_READ,
        Capability.PHASE_ADVANCE,
        Capability.FEEDBACK_SUBMIT,
    },
    Role.EQUITY_PARTNER: {
        Capability.DEAL_READ,  # scoped to shared deals — D-24 narrows this
        Capability.FEEDBACK_SUBMIT,
    },
    Role.ANALYST: {
        Capability.DEAL_READ,
        Capability.DEAL_WRITE,
        Capability.MAPPING_CONFIRM,
        Capability.FEEDBACK_SUBMIT,
    },
}


def has_capability(role: Role, capability: Capability) -> bool:
    return capability in _MATRIX.get(role, set())


def _emails(raw: str) -> set[str]:
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def role_for_email(email: str) -> Role | None:
    """Map an authenticated email to its role from config (None if not provisioned).

    Read live from settings so role lists can change via config without a code change;
    matching is case-insensitive. The most-privileged matching list wins.
    """
    from .config import settings

    e = email.strip().lower()
    if e in _emails(settings.admin_emails):
        return Role.ADMIN
    if e in _emails(settings.executive_emails):
        return Role.EXECUTIVE
    if e in _emails(settings.equity_partner_emails):
        return Role.EQUITY_PARTNER
    if e in _emails(settings.analyst_emails):
        return Role.ANALYST
    return None


def require(*capabilities: Capability) -> Callable[..., Any]:
    """Build a FastAPI dependency that requires all the given capabilities.

    Imported lazily to avoid a circular import with ``auth``.
    """
    from .auth import Principal, get_current_principal

    async def _dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        missing = [c for c in capabilities if not has_capability(principal.role, c)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "forbidden",
                        "message": "Insufficient role for this action.",
                        "detail": {"missing": [c.value for c in missing]},
                    }
                },
            )
        return principal

    return _dependency

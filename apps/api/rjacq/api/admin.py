"""Admin: view and set integration API keys (design doc §2 admin; ADR-0012).

Admin-only. Keys are stored encrypted (``core/app_config``) and override the environment value
at request time — no redeploy needed to fix or rotate a key. The stored secret is never
returned; responses carry only configured/source/hint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import app_config
from ..core.auth import Principal
from ..core.db import get_session
from ..core.logging import get_logger
from ..core.rbac import Capability, require
from ..schemas.admin import IntegrationStatus, IntegrationUpdate

router = APIRouter(tags=["admin"])
log = get_logger("admin")


def _to_schema(s: app_config.IntegrationStatus) -> IntegrationStatus:
    return IntegrationStatus(
        key=s.key, label=s.label, configured=s.configured, source=s.source, hint=s.hint
    )


async def _status_for(session: AsyncSession, key: str) -> IntegrationStatus:
    for s in await app_config.list_status(session):
        if s.key == key:
            return _to_schema(s)
    raise HTTPException(  # unreachable for known keys
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": {"code": "not_found", "message": "Unknown integration key."}},
    )


@router.get("/admin/integrations", response_model=list[IntegrationStatus])
async def list_integrations(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.SETTINGS_MANAGE)),
) -> list[IntegrationStatus]:
    """Configured/missing status for every managed integration key (never the value)."""
    return [_to_schema(s) for s in await app_config.list_status(session)]


@router.put("/admin/integrations/{key}", response_model=IntegrationStatus)
async def set_integration(
    key: str,
    body: IntegrationUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.SETTINGS_MANAGE)),
) -> IntegrationStatus:
    """Set/replace an integration key (encrypted at rest; takes effect immediately)."""
    if not app_config.is_managed(key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Unknown integration key."}},
        )
    value = body.value.strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "empty_value", "message": "Provide a non-empty value."}},
        )
    await app_config.set_secret(session, key, value, actor=principal.email)
    await session.commit()
    log.info("integration_key_set", key=key, actor=principal.email)  # name only, never the value
    return await _status_for(session, key)


@router.delete("/admin/integrations/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_integration(
    key: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.SETTINGS_MANAGE)),
) -> None:
    """Remove an admin override so the environment value applies again."""
    if not app_config.is_managed(key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Unknown integration key."}},
        )
    await app_config.clear_secret(session, key)
    await session.commit()
    log.info("integration_key_cleared", key=key, actor=principal.email)

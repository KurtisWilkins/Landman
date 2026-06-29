"""Global default-rules config endpoints (defaults engine, Part 2b) — the admin rule library.

Read is open to any authenticated user (so the budget UI can show the live rates); editing is
admin-only (`SETTINGS_MANAGE`). Edits are global — they change the default everywhere it isn't
manually overridden on a deal.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import Principal, get_current_principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..models.defaults import DefaultRuleConfig
from ..schemas.defaults import DefaultRulePatch, DefaultRuleRow, DefaultRulesDoc
from ..underwriting import defaults_config

router = APIRouter(tags=["defaults-config"])


def _row(rc: DefaultRuleConfig) -> DefaultRuleRow:
    return DefaultRuleRow(
        rule_key=rc.rule_key,
        label=rc.label,
        rule_type=rc.rule_type,
        value=rc.value,
        target_account_code=rc.target_account_code,
        basis=rc.basis,
        is_income_offset=rc.is_income_offset,
        overrides_actuals=rc.overrides_actuals,
        driver_account_code=rc.driver_account_code,
        soft_min=rc.soft_min,
        soft_max=rc.soft_max,
        must_fix=rc.must_fix,
        enabled=rc.enabled,
    )


@router.get("/default-rules", response_model=DefaultRulesDoc)
async def list_default_rules(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> DefaultRulesDoc:
    """The global defaults rule library (seeded from RULE_LIBRARY on first read)."""
    rows = await defaults_config.list_rules(session)
    return DefaultRulesDoc(rules=[_row(r) for r in rows])


@router.put("/default-rules/{rule_key}", response_model=DefaultRuleRow)
async def update_default_rule(
    rule_key: str,
    body: DefaultRulePatch,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.SETTINGS_MANAGE)),
) -> DefaultRuleRow:
    """Edit a rule's rate/amount, enabled flag, basis, recommended band, or override behavior —
    globally. The change takes effect on the next budget recompute (manual lines untouched)."""
    try:
        row = await defaults_config.update_rule(
            session,
            rule_key,
            value=body.value,
            enabled=body.enabled,
            basis=body.basis,
            soft_min=body.soft_min,
            soft_max=body.soft_max,
            overrides_actuals=body.overrides_actuals,
            actor=principal.user_id,
        )
    except defaults_config.DefaultRuleError as exc:
        code = status.HTTP_404_NOT_FOUND if exc.code == "not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=code, detail={"error": {"code": exc.code, "message": exc.message}}
        ) from exc
    return _row(row)

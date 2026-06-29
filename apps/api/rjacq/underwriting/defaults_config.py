"""Resolver + CRUD for the global default-rules config (defaults engine, Part 2b).

`effective_rules` is the single seam the budget engine reads: the admin-editable DB rows when
present, else the code `RULE_LIBRARY` (so a fresh DB behaves identically until seeded). Seeding is
an idempotent upsert from `RULE_LIBRARY`; admins edit rates/amounts/enabled per rule, globally.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.defaults import DefaultRuleConfig
from .defaults_rules import RULE_LIBRARY, RuleSpec, RuleType


class DefaultRuleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _to_spec(row: DefaultRuleConfig) -> RuleSpec:
    return RuleSpec(
        rule_key=row.rule_key,
        label=row.label,
        rule_type=RuleType(row.rule_type),
        value=row.value,
        target_account_code=row.target_account_code,
        basis=row.basis,
        is_income_offset=row.is_income_offset,
        overrides_actuals=row.overrides_actuals,
        driver_account_code=row.driver_account_code,
        soft_min=row.soft_min,
        soft_max=row.soft_max,
        must_fix=row.must_fix,
        enabled=row.enabled,
    )


def _row_kwargs(spec: RuleSpec, sort: int) -> dict[str, object]:
    return {
        "label": spec.label,
        "rule_type": spec.rule_type.value,
        "value": spec.value,
        "target_account_code": spec.target_account_code,
        "basis": spec.basis,
        "is_income_offset": spec.is_income_offset,
        "overrides_actuals": spec.overrides_actuals,
        "driver_account_code": spec.driver_account_code,
        "soft_min": spec.soft_min,
        "soft_max": spec.soft_max,
        "must_fix": spec.must_fix,
        "enabled": spec.enabled,
        "sort": sort,
    }


async def _rows(session: AsyncSession) -> list[DefaultRuleConfig]:
    stmt = select(DefaultRuleConfig)
    rows = list((await session.execute(stmt)).scalars().all())
    return sorted(rows, key=lambda r: (r.sort if r.sort is not None else 9999, r.rule_key))


async def effective_rules(session: AsyncSession) -> list[RuleSpec]:
    """The live rule specs the budget engine applies: DB overlay when seeded, else the code
    library (so behavior is identical until an admin customizes)."""
    rows = await _rows(session)
    if not rows:
        return list(RULE_LIBRARY)
    return [_to_spec(r) for r in rows]


async def seed_rules(session: AsyncSession) -> None:
    """Upsert `RULE_LIBRARY` into the config table (idempotent — only inserts missing rules; never
    overwrites an admin edit). Caller commits."""
    existing = {r.rule_key for r in await _rows(session)}
    for sort, spec in enumerate(RULE_LIBRARY):
        if spec.rule_key in existing:
            continue
        session.add(DefaultRuleConfig(rule_key=spec.rule_key, **_row_kwargs(spec, sort)))


async def list_rules(session: AsyncSession) -> list[DefaultRuleConfig]:
    """All config rows (seeded from `RULE_LIBRARY` on first read so the admin UI is never empty)."""
    rows = await _rows(session)
    if not rows:
        await seed_rules(session)
        await session.commit()
        rows = await _rows(session)
    return rows


async def update_rule(
    session: AsyncSession,
    rule_key: str,
    *,
    value: Decimal | None = None,
    enabled: bool | None = None,
    basis: str | None = None,
    soft_min: Decimal | None = None,
    soft_max: Decimal | None = None,
    overrides_actuals: bool | None = None,
    actor: str | None = None,
) -> DefaultRuleConfig:
    """Edit a rule's tunables globally (rate/amount, enabled, band, override). The rule TYPE and
    target GL are intentionally not editable here — those are structural."""
    await list_rules(session)  # ensure seeded
    row = await session.get(DefaultRuleConfig, rule_key)
    if row is None:
        raise DefaultRuleError("not_found", f"No such default rule {rule_key}.")
    if value is not None:
        row.value = value
    if enabled is not None:
        row.enabled = enabled
    if basis is not None:
        if basis not in ("annual", "monthly"):
            raise DefaultRuleError("invalid_basis", "basis must be 'annual' or 'monthly'.")
        row.basis = basis
    if soft_min is not None:
        row.soft_min = soft_min
    if soft_max is not None:
        row.soft_max = soft_max
    if overrides_actuals is not None:
        row.overrides_actuals = overrides_actuals
    row.updated_at = datetime.now(UTC)
    row.updated_by = actor
    await session.commit()
    return row

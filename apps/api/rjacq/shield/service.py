"""SHIELD sync service: aggregate baselines and seed each deal's assumptions.

Writes only to *our* Postgres (never SHIELD). Seeding preserves provenance: an existing
operator override is never clobbered — only the SHIELD baseline is refreshed.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..models.underwriting import Assumption
from .baseline import MetricSpec, aggregate_baselines
from .connector import ShieldConnector

log = get_logger("shield")


async def seed_assumptions(
    session: AsyncSession,
    deal_id: str,
    baselines: dict[str, Decimal],
    specs: Sequence[MetricSpec],
) -> int:
    """Upsert baseline assumptions for a deal. An existing override is preserved (only the
    baseline_value / shield_source / label are refreshed)."""
    by_key = {s.key: s for s in specs}
    existing = {
        a.key: a
        for a in (await session.execute(select(Assumption).where(Assumption.deal_id == deal_id)))
        .scalars()
        .all()
    }
    written = 0
    for key, value in baselines.items():
        spec = by_key.get(key)
        if spec is None:
            continue
        row = existing.get(key)
        if row is None:
            session.add(
                Assumption(
                    assumption_id=f"as_{uuid.uuid4().hex[:16]}",
                    deal_id=deal_id,
                    key=key,
                    label=spec.label,
                    baseline_value=value,
                    shield_source=spec.shield_source,
                    is_overridden=False,
                )
            )
        else:
            # Refresh the baseline; never disturb an operator override (provenance).
            row.baseline_value = value
            row.shield_source = spec.shield_source
            row.label = spec.label
        written += 1
    await session.flush()
    return written


async def sync_baselines(
    session: AsyncSession,
    *,
    connector: ShieldConnector,
    query: str,
    specs: Sequence[MetricSpec],
    deal_ids: Sequence[str],
) -> dict[str, Decimal]:
    """Pull portfolio actuals (read-only), aggregate baselines, seed the given deals."""
    rows = connector.fetch_all(query)  # read-only; guarded in the connector
    baselines = aggregate_baselines(rows, specs)
    for deal_id in deal_ids:
        await seed_assumptions(session, deal_id, baselines, specs)
    log.info("shield.baselines_synced", metrics=len(baselines), deals=len(deal_ids))
    return baselines

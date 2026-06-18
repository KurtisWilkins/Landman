"""SHIELD sync service: aggregate baselines and seed each acquisition's assumptions.

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
    acquisition_id: str,
    baselines: dict[str, Decimal],
    specs: Sequence[MetricSpec],
) -> int:
    """Upsert baseline assumptions for a acquisition. An existing override is preserved (only the
    baseline_value / shield_source / label are refreshed)."""
    by_key = {s.key: s for s in specs}
    existing = {
        a.key: a
        for a in (
            await session.execute(
                select(Assumption).where(Assumption.acquisition_id == acquisition_id)
            )
        )
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
                    acquisition_id=acquisition_id,
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
    acquisition_ids: Sequence[str],
) -> dict[str, Decimal]:
    """Pull portfolio actuals (read-only), aggregate baselines, seed the given acquisitions."""
    rows = connector.fetch_all(query)  # read-only; guarded in the connector
    baselines = aggregate_baselines(rows, specs)
    for acquisition_id in acquisition_ids:
        await seed_assumptions(session, acquisition_id, baselines, specs)
    log.info("shield.baselines_synced", metrics=len(baselines), acquisitions=len(acquisition_ids))
    return baselines

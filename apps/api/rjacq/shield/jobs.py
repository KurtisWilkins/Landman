"""Scheduled SHIELD baseline-sync job (Arq).

Registered with the worker once SHIELD is configured. No-ops (logs and returns) when C-14
connection details or the C-15 metric set are unresolved — it never guesses.
"""

from __future__ import annotations

from typing import Any

from ..core.config import settings
from ..core.logging import get_logger
from .connector import build_shield_connector

log = get_logger("shield")


async def sync_shield_baselines(ctx: dict[str, Any]) -> str:
    """Pull SHIELD portfolio actuals → baseline metrics → seed deal assumptions.

    Wiring note: the SELECT to run and the deal set are config/operational inputs tied to
    C-14/C-15; this entrypoint is intentionally inert until those are provided, so the worker
    can register it safely today.
    """
    connector = build_shield_connector()
    if connector is None:
        log.info("shield.sync.skipped", reason="not_configured", decision="C-14")
        return "skipped: SHIELD not configured (C-14)"
    if not settings.shield_baseline_metrics:
        log.info("shield.sync.skipped", reason="no_metric_spec", decision="C-15")
        return "skipped: no metric spec (C-15)"
    # The concrete query + deal selection land with C-14/C-15; until then we only verify
    # connectivity by snapshotting the schema (read-only).
    snapshot = connector.snapshot()
    log.info("shield.sync.connected", tables=len(snapshot))
    return f"connected: {len(snapshot)} tables visible"

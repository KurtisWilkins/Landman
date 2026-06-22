"""Redis/Arq job queue wiring (ingest, scraping, SHIELD sync, feedback dispatch).

Phase 0 establishes the connection + a health-check task. Real jobs are added by the
domain streams (ingestion, shield, comps, feedback) in later phases.
"""

from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from ..mapping.jobs import classify_acquisition_mappings
from ..shield.jobs import sync_shield_baselines
from .config import settings
from .logging import configure_logging, correlation_id_var, get_logger

log = get_logger("worker")


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def enqueue(function: str, *args: Any) -> bool:
    """Best-effort enqueue from the API. A queue hiccup must never fail the request that triggered
    it, so a connection/enqueue error is logged and swallowed (the work can be re-triggered)."""
    try:
        pool = await create_pool(redis_settings())
    except Exception as exc:  # redis unreachable / misconfigured
        log.warning("worker.enqueue_unavailable", function=function, error=type(exc).__name__)
        return False
    try:
        await pool.enqueue_job(function, *args)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("worker.enqueue_failed", function=function, error=type(exc).__name__)
        return False
    finally:
        await pool.close()


async def healthcheck(ctx: dict[str, Any]) -> str:
    """Trivial task proving the queue round-trips end to end."""
    log.info("worker.healthcheck", job_id=ctx.get("job_id"))
    return "ok"


async def on_startup(ctx: dict[str, Any]) -> None:
    configure_logging(level="INFO" if settings.is_production else "DEBUG")
    log.info("worker.startup")


async def on_job_start(ctx: dict[str, Any]) -> None:
    # Thread a correlation ID per job so worker logs join the same flow as HTTP logs.
    correlation_id_var.set(str(ctx.get("job_id", "")))


class WorkerSettings:
    """Arq worker entrypoint: ``arq rjacq.core.queue.WorkerSettings``.

    Domain jobs are registered here (the worker is the composition root). The SHIELD sync
    no-ops until C-14/C-15 are configured (see shield.jobs).
    """

    functions = [healthcheck, sync_shield_baselines, classify_acquisition_mappings]
    on_startup = on_startup
    on_job_start = on_job_start
    redis_settings = redis_settings()

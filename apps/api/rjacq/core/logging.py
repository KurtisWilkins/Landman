"""Structured JSON logging with a correlation ID threaded through every flow.

Used by the HTTP app (via middleware) and by Arq workers. Per CLAUDE.md: JSON logs
only; never log secrets, credentials, full financials, or raw feedback screenshots.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import cast

import structlog
from structlog.types import EventDict, WrappedLogger

# Correlation ID is set per HTTP request / per worker job and bound to every log line.
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def _add_correlation_id(_logger: WrappedLogger, _name: str, event_dict: EventDict) -> EventDict:
    cid = correlation_id_var.get()
    if cid is not None:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib for JSON output. Idempotent."""
    logging.basicConfig(format="%(message)s", level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_correlation_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))

"""Sentry initialization for the API and workers, tagged by release/build hash.

[DECISION] C-30: error-tracking provider + data-residency. Sentry is the default per the
design doc; if it changes, swap here. No-op when ``SENTRY_DSN`` is unset.
"""

from __future__ import annotations

from .config import settings


def init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        release=settings.release,  # ties every error to a deploy
        traces_sample_rate=0.1,
        send_default_pii=False,  # never ship PII/financials to the tracker
    )

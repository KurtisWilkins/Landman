"""Admin-managed integration keys, encrypted at rest in the DB (ADR-0012).

A small set of integration API keys can be set by an admin through the in-app Settings UI.
Values are Fernet-encrypted with a key derived from ``settings.secret_key`` and stored in
``app_secrets``; they override the environment value at request time (so a key can be fixed
or rotated with no redeploy/restart). The plaintext is never returned to clients — the UI sees
only "configured" + a last-4 hint.

Scope is deliberately the integration/API keys (not infra secrets like DATABASE_URL or
SECRET_KEY — editing those from the UI could take the app down).
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.app_secret import AppSecret
from .config import settings


@dataclass(frozen=True)
class IntegrationKey:
    key: str  # also the Settings attribute name it overrides
    label: str


# The keys the admin UI manages. ``key`` matches the Settings attribute (and UPPER env var).
INTEGRATION_KEYS: list[IntegrationKey] = [
    IntegrationKey("anthropic_api_key", "Anthropic API key (PDF/OM extraction, AI)"),
    IntegrationKey("voyage_api_key", "Voyage embeddings key (GL mapping)"),
    IntegrationKey("population_provider_api_key", "Population / Census provider key"),
    IntegrationKey("google_places_api_key", "Google Places key (comps)"),
    IntegrationKey("yelp_api_key", "Yelp key (comps)"),
    IntegrationKey("tripadvisor_api_key", "TripAdvisor key (comps)"),
]
_KNOWN = {k.key: k for k in INTEGRATION_KEYS}


def is_managed(key: str) -> bool:
    return key in _KNOWN


def _fernet() -> Fernet:
    # Deterministic 32-byte key from the app secret. Rotating SECRET_KEY invalidates stored
    # values (they'd need re-entry) — documented in ADR-0012.
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


async def get_override(session: AsyncSession, key: str) -> str | None:
    """Decrypted admin-set value for ``key``, or None if not set / undecryptable."""
    row = await session.get(AppSecret, key)
    if row is None:
        return None
    try:
        return _fernet().decrypt(row.value_encrypted).decode("utf-8")
    except (InvalidToken, ValueError):
        return None  # SECRET_KEY changed since it was stored — treat as unset


async def effective_secret(session: AsyncSession, key: str) -> str | None:
    """Admin DB override if set, else the environment/Settings value."""
    override = await get_override(session, key)
    if override:
        return override
    value = getattr(settings, key, None)
    return value or None


async def set_secret(session: AsyncSession, key: str, value: str, *, actor: str | None) -> None:
    """Encrypt and upsert an admin-set integration key (caller commits)."""
    token = _fernet().encrypt(value.encode("utf-8"))
    last4 = value[-4:] if len(value) >= 4 else None
    row = await session.get(AppSecret, key)
    if row is None:
        session.add(AppSecret(key=key, value_encrypted=token, last4=last4, updated_by=actor))
    else:
        row.value_encrypted = token
        row.last4 = last4
        row.updated_by = actor


async def clear_secret(session: AsyncSession, key: str) -> None:
    """Remove an admin override so the env value applies again (caller commits)."""
    row = await session.get(AppSecret, key)
    if row is not None:
        await session.delete(row)


@dataclass(frozen=True)
class IntegrationStatus:
    key: str
    label: str
    configured: bool
    source: str | None  # "database" | "environment" | None
    hint: str | None  # last-4 of the value, when known


async def list_status(session: AsyncSession) -> list[IntegrationStatus]:
    """Status for every managed key — never the secret value, only configured/source/hint."""
    overrides = {row.key: row for row in (await session.execute(select(AppSecret))).scalars()}
    out: list[IntegrationStatus] = []
    for k in INTEGRATION_KEYS:
        db_row = overrides.get(k.key)
        env_val = getattr(settings, k.key, None)
        if db_row is not None:
            out.append(IntegrationStatus(k.key, k.label, True, "database", db_row.last4))
        elif env_val:
            out.append(IntegrationStatus(k.key, k.label, True, "environment", str(env_val)[-4:]))
        else:
            out.append(IntegrationStatus(k.key, k.label, False, None, None))
    return out

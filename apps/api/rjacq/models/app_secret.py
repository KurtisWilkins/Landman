"""Admin-managed integration secret, encrypted at rest (ADR-0012).

Operational config — NOT part of the §8 data contract. Holds API keys an admin sets through
the in-app Settings UI; the value is Fernet-encrypted (``core/app_config.py``) and overrides the
environment value at runtime. ``last4`` is a plaintext hint for the masked UI; the plaintext key
is never stored or returned.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, updated_at_column


class AppSecret(Base):
    __tablename__ = "app_secrets"

    key: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "anthropic_api_key"
    value_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    last4: Mapped[str | None] = mapped_column(String)  # masked display hint
    updated_by: Mapped[str | None] = mapped_column(String)  # admin email (provenance)
    updated_at: Mapped[datetime] = updated_at_column()

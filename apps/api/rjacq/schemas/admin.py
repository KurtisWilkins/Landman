"""Admin / integration-key schemas. Secret values are never returned — only status."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IntegrationStatus(BaseModel):
    key: str
    label: str
    configured: bool
    source: str | None = None  # "database" | "environment" | None
    hint: str | None = None  # last 4 chars of the configured value, when known


class IntegrationUpdate(BaseModel):
    value: str = Field(min_length=1)

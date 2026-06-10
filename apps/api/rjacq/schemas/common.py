"""Shared schema primitives."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base for all wire models: populate from ORM attributes, forbid unknown fields out."""

    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Structured error envelope (CLAUDE.md API design)."""

    error: ErrorDetail

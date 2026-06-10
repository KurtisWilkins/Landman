"""Helpers shared by model modules."""

from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum


def pg_enum[E: enum.Enum](py_enum: type[E], name: str) -> SAEnum:
    """A native PostgreSQL enum that stores the enum *value* (the §8.2 string)."""
    return SAEnum(
        py_enum,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        native_enum=True,
    )

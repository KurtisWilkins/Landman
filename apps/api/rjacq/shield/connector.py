"""Read-only SHIELD connector.

A ``ShieldConnector`` exposes only reads. The concrete connector additionally guards every
query so a non-SELECT can never reach SHIELD (defense in depth on top of least-privilege
read-only credentials). The factory returns ``None`` until C-14 connection details are
configured, so callers degrade gracefully rather than guessing.
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

from ..core.config import settings

# A query must begin with SELECT/WITH and contain no data-/schema-mutating keyword.
_READ_PREFIX = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|grant|exec|call)\b",
    re.IGNORECASE,
)


class ShieldReadOnlyError(RuntimeError):
    """Raised when a non-read query is attempted against SHIELD."""


def assert_read_only(query: str) -> None:
    """Reject anything that isn't a pure read. SHIELD is never written to."""
    if not _READ_PREFIX.match(query) or _FORBIDDEN.search(query):
        raise ShieldReadOnlyError("Only read-only SELECT/WITH queries are allowed on SHIELD.")


@runtime_checkable
class ShieldConnector(Protocol):
    def fetch_all(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...

    def snapshot(self) -> dict[str, list[str]]: ...


class SqlAlchemyShieldConnector:
    """Concrete read-only connector over a SQLAlchemy SQL Server engine.

    The ODBC driver (e.g. ``mssql+pyodbc``) is provided by the deploy environment (C-14);
    we do not vendor pyodbc. The engine is created lazily and only when SHIELD is configured.
    """

    def __init__(self, url: str) -> None:
        from sqlalchemy import create_engine

        # Read-only by credential + by guard below; pool kept small for a scheduled sync.
        self._engine = create_engine(url, pool_size=1, max_overflow=0, pool_pre_ping=True)

    def fetch_all(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        assert_read_only(query)
        from sqlalchemy import text

        with self._engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            return [dict(row) for row in result.mappings()]

    def snapshot(self) -> dict[str, list[str]]:
        """Table → column-name list, for drift detection."""
        rows = self.fetch_all(
            "SELECT table_name, column_name FROM information_schema.columns "
            "ORDER BY table_name, ordinal_position"
        )
        out: dict[str, list[str]] = {}
        for r in rows:
            out.setdefault(str(r["table_name"]), []).append(str(r["column_name"]))
        return out


def build_shield_connector() -> ShieldConnector | None:
    """Construct the connector from config, or None when C-14 is unresolved.

    TODO(decision: §14 C-14): confirm SHIELD host/db/credentials + network reachability and
    the ODBC driver string. Until then this returns None and the sync job no-ops.
    """
    if not (
        settings.shield_host
        and settings.shield_db
        and settings.shield_readonly_user
        and settings.shield_readonly_password
    ):
        return None
    url = (
        f"mssql+pyodbc://{settings.shield_readonly_user}:{settings.shield_readonly_password}"
        f"@{settings.shield_host}:{settings.shield_port}/{settings.shield_db}"
        "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes"
    )
    return SqlAlchemyShieldConnector(url)

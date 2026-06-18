"""Guardrail: migrations must not silently destroy production data (CLAUDE.md, data-safety).

Now that production carries live deal data, a forward migration (``upgrade()``) must never drop a
table/column/type or otherwise destroy data unless a human has *explicitly* acknowledged it with
an ``# allow-destructive: <reason>`` marker. ``downgrade()`` bodies are exempt — they're expected
to undo a migration and are never run against prod. This test fails CI if an un-acknowledged
destructive op reaches an ``upgrade()``.
"""

from __future__ import annotations

import ast
import pathlib
import re

# Repo root is three levels up from apps/api/tests/.
_MIGRATIONS = pathlib.Path(__file__).resolve().parents[3] / "migrations" / "versions"

# Alembic op helpers and raw-SQL fragments that destroy data/objects.
_DESTRUCTIVE_CALLS = ("drop_table", "drop_column", "drop_constraint", "drop_index")
_DESTRUCTIVE_SQL = re.compile(r"\bDROP\s+(TABLE|COLUMN|TYPE|INDEX|CONSTRAINT|EXTENSION)\b", re.I)
_ALLOW_MARKER = "allow-destructive"


def _upgrade_source(path: pathlib.Path) -> str | None:
    """Return the source lines of the module's ``upgrade()`` function, or None if absent.

    Sliced by line range (upgrade start → next top-level def / EOF) rather than via
    ``ast.get_source_segment`` so trailing inline comments — like an ``# allow-destructive``
    marker on the function's last line — are preserved.
    """
    text = path.read_text()
    lines = text.splitlines()
    tops = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)]
    for i, node in enumerate(tops):
        if node.name == "upgrade":
            end = tops[i + 1].lineno - 1 if i + 1 < len(tops) else len(lines)
            return "\n".join(lines[node.lineno - 1 : end])
    return None


def test_no_unacknowledged_destructive_ops_in_upgrades() -> None:
    violations: list[str] = []
    migration_files = sorted(p for p in _MIGRATIONS.glob("*.py") if p.name != "__init__.py")
    assert migration_files, "no migration files found — check the migrations path"

    for path in migration_files:
        src = _upgrade_source(path)
        if src is None:
            continue
        for raw_line in src.splitlines():
            line = raw_line.strip()
            if _ALLOW_MARKER in line:
                continue  # explicitly acknowledged by a human
            hit = any(f".{call}(" in line for call in _DESTRUCTIVE_CALLS) or bool(
                _DESTRUCTIVE_SQL.search(line)
            )
            if hit:
                violations.append(f"{path.name}: {line}")

    assert not violations, (
        "Destructive op in a migration upgrade() without an `# allow-destructive: <reason>` "
        "marker. Production has live data — add the marker only after confirming a backup and "
        "that the data loss is intended:\n  " + "\n  ".join(violations)
    )

"""Normalize parsed rows into typed records (design doc §5.2).

Columns vary by seller, so we locate the description/amount/type/count columns heuristically.
Numbers that don't parse are skipped rather than failing the ingest (greedy, graceful).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

Row = dict[str, str]

_DESC_HINTS = ("account", "description", "line item", "category", "gl", "name")
_AMOUNT_HINTS = ("amount", "total", "balance", "actual", "ytd", "annual")
_UNIT_TYPE_HINTS = ("unit_type", "site type", "type", "unit")
_COUNT_HINTS = ("count", "sites", "qty", "quantity", "spaces", "units")


@dataclass(frozen=True)
class ParsedLine:
    seller_source_line: str
    amount: Decimal | None
    raw: Row = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedUnit:
    unit_type: str
    count: int | None
    raw: Row = field(default_factory=dict)


def to_decimal(value: str) -> Decimal | None:
    """Parse a money/number cell. Handles $, commas, and (parenthesized) negatives."""
    s = value.strip().replace("$", "").replace(",", "")
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return -d if neg else d


def _pick_column(headers: Sequence[str], hints: Sequence[str]) -> str | None:
    for h in headers:
        hl = h.strip().lower()
        if any(hint in hl for hint in hints):
            return h
    return None


def _first_numeric_column(headers: Sequence[str], rows: Sequence[Row]) -> str | None:
    for h in headers:
        hits = sum(1 for r in rows if to_decimal(r.get(h, "")) is not None)
        if rows and hits >= max(1, len(rows) // 2):
            return h
    return None


def pnl_to_lines(headers: Sequence[str], rows: Sequence[Row]) -> list[ParsedLine]:
    desc_col = _pick_column(headers, _DESC_HINTS) or (headers[0] if headers else None)
    amount_col = _pick_column(headers, _AMOUNT_HINTS) or _first_numeric_column(headers, rows)
    lines: list[ParsedLine] = []
    for r in rows:
        label = (r.get(desc_col, "") if desc_col else "").strip()
        if not label:
            continue
        amount = to_decimal(r.get(amount_col, "")) if amount_col else None
        lines.append(ParsedLine(seller_source_line=label, amount=amount, raw=dict(r)))
    return lines


def unit_mix_to_units(headers: Sequence[str], rows: Sequence[Row]) -> list[ParsedUnit]:
    type_col = _pick_column(headers, _UNIT_TYPE_HINTS) or (headers[0] if headers else None)
    count_col = _pick_column(headers, _COUNT_HINTS) or _first_numeric_column(headers, rows)
    units: list[ParsedUnit] = []
    for r in rows:
        utype = (r.get(type_col, "") if type_col else "").strip()
        if not utype:
            continue
        count_dec = to_decimal(r.get(count_col, "")) if count_col else None
        units.append(
            ParsedUnit(
                unit_type=utype,
                count=int(count_dec) if count_dec is not None else None,
                raw=dict(r),
            )
        )
    return units

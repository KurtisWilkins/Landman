"""QuickBooks-style 'N Month Recap' P&L parsing (design doc §5.2).

These exports don't fit the header+columns model the generic parser assumes:

  * title rows precede the data (``Profit & Loss 12 Month Recap``, property, basis);
  * the real header is **month-columnar** with a blank first cell (``JUN 25 … TOTAL``);
  * account names are indented in column A with the GL code embedded
    (``      410130 Storage Fees``); and
  * section (``Income``/``Expense``), non-posting group, and ``Total …`` subtotal rows are
    interleaved with the posting lines.

We locate the month-header row, then load each **leaf posting line** — a row that carries
monthly values and whose label is not a ``Total …`` subtotal — summing the month columns into a
trailing-period amount. The original (indented) label and every per-month value are retained in
``raw`` as provenance; nothing is dropped to simplify (CLAUDE.md golden rule #4).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal

from .records import ParsedLine, to_decimal

# A month-column header cell: a month name (abbrev or full) followed by a 2–4 digit year,
# e.g. "JUN 25", "January 2026", "Jun-25".
_MONTH_RE = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?[\s\-']*\d{2,4}$"
)

# Top-level section labels (value-less header rows) we track for provenance/sign context.
_SECTIONS = {
    "income",
    "expense",
    "expenses",
    "other income",
    "other expense",
    "cost of goods sold",
}


def _cell(value: object) -> str:
    return "" if value is None else str(value).strip()


def _is_month(text: str) -> bool:
    return bool(_MONTH_RE.match(text.strip().lower()))


def find_header_row(matrix: Sequence[Sequence[object]]) -> int | None:
    """Index of the month-columnar header row (≥3 month cells + a TOTAL), or None.

    Only the first rows are scanned — the header sits just under the title block.
    """
    for i, row in enumerate(matrix[:15]):
        cells = [_cell(c) for c in row]
        months = sum(1 for c in cells if _is_month(c))
        has_total = any(c.lower() == "total" for c in cells)
        if months >= 3 and has_total:
            return i
    return None


def is_recap(matrix: Sequence[Sequence[object]]) -> bool:
    return find_header_row(matrix) is not None


def recap_to_lines(matrix: Sequence[Sequence[object]]) -> list[ParsedLine]:
    """Leaf posting lines from a recap matrix; subtotals, group + section rows excluded."""
    header_idx = find_header_row(matrix)
    if header_idx is None:
        return []
    header = [_cell(c) for c in matrix[header_idx]]
    # Value columns are the month columns only — summing them yields the trailing-period
    # figure. The trailing TOTAL column is intentionally excluded (avoids double counting).
    month_cols = [j for j, c in enumerate(header) if _is_month(c)]

    lines: list[ParsedLine] = []
    section = ""
    for row in matrix[header_idx + 1 :]:
        cells = [_cell(c) for c in row]
        label = cells[0].strip() if cells else ""
        values: list[tuple[str, str, Decimal]] = []
        for j in month_cols:
            raw_val = cells[j] if j < len(cells) else ""
            dec = to_decimal(raw_val)
            if dec is not None:
                values.append((header[j], raw_val, dec))

        if not values:
            # A value-less row is a section header, a non-posting group header, or a blank.
            if label.lower() in _SECTIONS:
                section = label
            continue
        if label.lower().startswith("total"):
            continue  # subtotal — already represented by its leaf lines

        amount = sum((d for _, _, d in values), Decimal("0"))
        raw: dict[str, str] = {month: val for month, val, _ in values}
        raw["_seller_line"] = label
        if section:
            raw["_section"] = section  # keep income/expense context (provenance)
        lines.append(ParsedLine(seller_source_line=label, amount=amount, raw=raw))
    return lines

"""Ingestion service (design doc §5.2): detect → parse → normalized load.

Greedy ingest, graceful degradation: an unrecognized sheet is reported (loaded 0), never an
error; one bad file never blocks a acquisition.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from . import load
from .detect import detect_sheet_type
from .extractor import PdfExtractor
from .parse import parse_matrix, parse_tabular
from .recap import is_recap, recap_to_lines
from .records import pnl_to_lines, unit_mix_to_units

log = get_logger("ingestion")


class IngestError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class IngestResult:
    sheet_type: str
    financial_lines_loaded: int = 0
    units_loaded: int = 0
    units_skipped: int = 0
    period_id: str | None = None
    note: str | None = None


def _is_pdf(content_type: str, filename: str) -> bool:
    return "pdf" in content_type.lower() or filename.lower().endswith(".pdf")


async def ingest_document(
    session: AsyncSession,
    acquisition_id: str,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    pdf_extractor: PdfExtractor | None = None,
    period_label: str = "ingested",
) -> IngestResult:
    if _is_pdf(content_type, filename):
        if pdf_extractor is None:
            raise IngestError(
                "pdf_extractor_not_configured", "PDF extraction not configured (C-20)."
            )
        lines = pdf_extractor.extract_pnl(data)
        period_id, n = await load.load_pnl(
            session,
            acquisition_id,
            period_label=period_label,
            lines=lines,
            source_filename=filename,
        )
        log.info("ingestion.pdf_loaded", acquisition_id=acquisition_id, lines=n)
        return IngestResult(sheet_type="pnl", financial_lines_loaded=n, period_id=period_id)

    # A QuickBooks 'N Month Recap' P&L doesn't fit the header+columns model (its header isn't
    # row 0 and it's month-columnar) — detect and normalize it from the raw cell matrix first.
    matrix = parse_matrix(data, content_type, filename)
    if is_recap(matrix):
        lines = recap_to_lines(matrix)
        period_id, n = await load.load_pnl(
            session,
            acquisition_id,
            period_label=period_label,
            lines=lines,
            source_filename=filename,
        )
        log.info("ingestion.recap_loaded", acquisition_id=acquisition_id, lines=n)
        return IngestResult(sheet_type="pnl", financial_lines_loaded=n, period_id=period_id)

    headers, rows = parse_tabular(data, content_type, filename)
    sheet_type = detect_sheet_type(headers)
    log.info(
        "ingestion.detected", acquisition_id=acquisition_id, sheet_type=sheet_type, rows=len(rows)
    )

    if sheet_type == "pnl":
        lines = pnl_to_lines(headers, rows)
        period_id, n = await load.load_pnl(
            session,
            acquisition_id,
            period_label=period_label,
            lines=lines,
            source_filename=filename,
        )
        return IngestResult(sheet_type=sheet_type, financial_lines_loaded=n, period_id=period_id)

    if sheet_type == "unit_mix":
        units = unit_mix_to_units(headers, rows)
        loaded, skipped = await load.load_units(session, acquisition_id, units)
        return IngestResult(sheet_type=sheet_type, units_loaded=loaded, units_skipped=skipped)

    # rent_roll / booking / unknown: detected but not yet normalized — reported, not failed.
    return IngestResult(sheet_type=sheet_type, note="sheet type not yet normalized")

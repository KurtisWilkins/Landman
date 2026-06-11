"""Ingestion tests (§5.2): detection, parsing, normalized load, graceful degradation."""

from __future__ import annotations

import io
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from rjacq.ingestion import service as ingest
from rjacq.ingestion.detect import detect_sheet_type
from rjacq.ingestion.parse import parse_csv, parse_xlsx
from rjacq.ingestion.records import pnl_to_lines, to_decimal
from rjacq.ingestion.service import IngestError
from rjacq.models.deals import Deal
from rjacq.models.enums import DealStatus, MapConfidence, Phase, PropertyType
from rjacq.models.financials import FinancialLine
from rjacq.models.property import Unit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── detection ───────────────────────────────────────────────────────────────


def test_detect_sheet_types() -> None:
    assert detect_sheet_type(["Account", "Amount"]) == "pnl"
    assert detect_sheet_type(["Unit Type", "Count"]) == "unit_mix"
    assert detect_sheet_type(["Check In", "Check Out", "Nights"]) == "booking"
    assert detect_sheet_type(["Site", "Tenant", "Rent"]) == "rent_roll"
    assert detect_sheet_type(["Foo", "Bar"]) == "unknown"


# ── number parsing ──────────────────────────────────────────────────────────


def test_to_decimal_handles_money_formats() -> None:
    assert to_decimal("$2,680,000") == Decimal("2680000")
    assert to_decimal("(84,000)") == Decimal("-84000")
    assert to_decimal("0.48") == Decimal("0.48")
    assert to_decimal("n/a") is None
    assert to_decimal("") is None


# ── parsing ─────────────────────────────────────────────────────────────────


def test_parse_csv() -> None:
    headers, rows = parse_csv(b"Account,Amount\nSite Rental Income,2680000\nMarketing,96000\n")
    assert headers == ["Account", "Amount"]
    assert rows[0] == {"Account": "Site Rental Income", "Amount": "2680000"}
    assert len(rows) == 2


def test_pnl_to_lines_locates_columns() -> None:
    headers, rows = parse_csv(b"Account,Amount\nSite Rental Income,2680000\nBlank,\n")
    lines = pnl_to_lines(headers, rows)
    assert lines[0].seller_source_line == "Site Rental Income"
    assert lines[0].amount == Decimal("2680000")
    assert lines[1].amount is None  # missing amount doesn't fail the ingest


def test_parse_xlsx_roundtrip() -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Account", "Amount"])
    ws.append(["Utilities", 605400])
    buf = io.BytesIO()
    wb.save(buf)
    headers, rows = parse_xlsx(buf.getvalue())
    assert headers == ["Account", "Amount"]
    assert rows[0]["Account"] == "Utilities"


# ── normalized load (real Postgres) ─────────────────────────────────────────


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _deal(session: AsyncSession) -> str:
    deal_id = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Deal(
            deal_id=deal_id,
            name="Ingestion Test Park",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=DealStatus.ACTIVE,
        )
    )
    await session.flush()
    return deal_id


async def test_ingest_pnl_loads_unmapped_with_raw_payload(session: AsyncSession) -> None:
    deal_id = await _deal(session)
    csv = b"Account,Amount\nSite Rental Income,2680000\nMarketing,96000\n"
    result = await ingest.ingest_document(
        session, deal_id, filename="pnl.csv", content_type="text/csv", data=csv
    )
    assert result.sheet_type == "pnl"
    assert result.financial_lines_loaded == 2

    lines = (
        (await session.execute(select(FinancialLine).where(FinancialLine.deal_id == deal_id)))
        .scalars()
        .all()
    )
    assert len(lines) == 2
    first = next(line_ for line_ in lines if line_.seller_source_line == "Site Rental Income")
    assert first.account_code is None  # loaded unmapped
    assert first.map_confidence == MapConfidence.UNMAPPED
    assert first.amount == Decimal("2680000")
    assert first.raw_payload == {"Account": "Site Rental Income", "Amount": "2680000"}  # provenance


async def test_ingest_unit_mix_maps_known_skips_unknown(session: AsyncSession) -> None:
    deal_id = await _deal(session)
    csv = b"Unit Type,Count\nRV Pull-Through,96\nUFO Pad,3\n"
    result = await ingest.ingest_document(
        session, deal_id, filename="units.csv", content_type="text/csv", data=csv
    )
    assert result.sheet_type == "unit_mix"
    assert result.units_loaded == 1  # RV Pull-Through mapped
    assert result.units_skipped == 1  # UFO Pad unknown — skipped, not failed
    units = (await session.execute(select(Unit).where(Unit.deal_id == deal_id))).scalars().all()
    assert len(units) == 1


async def test_ingest_pdf_without_extractor_raises(session: AsyncSession) -> None:
    deal_id = await _deal(session)
    with pytest.raises(IngestError) as ei:
        await ingest.ingest_document(
            session, deal_id, filename="deal.pdf", content_type="application/pdf", data=b"%PDF-1.4"
        )
    assert ei.value.code == "pdf_extractor_not_configured"


async def test_ingest_unknown_sheet_is_reported_not_failed(session: AsyncSession) -> None:
    deal_id = await _deal(session)
    result = await ingest.ingest_document(
        session, deal_id, filename="misc.csv", content_type="text/csv", data=b"Foo,Bar\n1,2\n"
    )
    assert result.sheet_type == "unknown"
    assert result.financial_lines_loaded == 0
    assert result.note is not None

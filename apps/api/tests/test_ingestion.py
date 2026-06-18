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
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import AcquisitionStatus, MapConfidence, Phase, PropertyType
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


# ── QuickBooks 'N Month Recap' P&L (month-columnar, indented GL leaves) ───────


def _recap_csv() -> bytes:
    # Mirrors the QuickBooks layout: title rows, a month-columnar header, section + non-posting
    # group + Total subtotal rows interleaved with indented leaf accounts.
    return (
        b"Profit & Loss 3 Month Recap\n"
        b"Property: Ridgeview RV Resort LLC\n"
        b"Cash Basis\n"
        b"\n"
        b" ,JUN 25,JUL 25,AUG 25,TOTAL\n"
        b"Income\n"
        b"   412000 Rental Income - RV (Non-Posting)\n"
        b"      412130 RV Monthly,71077.76,73770.25,72403.28\n"
        b"      412140 RV Additional Fees,0,0,5.0\n"
        b"   Total 412000 Rental Income - RV (Non-Posting)\n"
        b"Total Income\n"
        b"\n"
        b"Expense\n"
        b"      540360 Sewer-Offset,-80.0,0,0\n"
        b"Total Expense\n"
    )


def test_recap_detection_and_leaf_extraction() -> None:
    from rjacq.ingestion.parse import parse_matrix
    from rjacq.ingestion.recap import find_header_row, is_recap, recap_to_lines

    matrix = parse_matrix(_recap_csv(), "text/csv", "recap.csv")
    assert is_recap(matrix)
    assert find_header_row(matrix) == 4  # month header sits under the title block

    lines = recap_to_lines(matrix)
    # Only the three leaf posting lines — section/group/Total rows excluded (no double count).
    assert [line.seller_source_line for line in lines] == [
        "412130 RV Monthly",
        "412140 RV Additional Fees",
        "540360 Sewer-Offset",
    ]
    by_label = {line.seller_source_line: line for line in lines}
    # Month columns summed into the trailing-period amount (TOTAL column ignored).
    assert by_label["412130 RV Monthly"].amount == Decimal("217251.29")
    assert by_label["412140 RV Additional Fees"].amount == Decimal("5.0")
    assert by_label["540360 Sewer-Offset"].amount == Decimal("-80.0")  # negatives kept
    # Section context retained as provenance; original label preserved.
    assert by_label["412130 RV Monthly"].raw["_section"] == "Income"
    assert by_label["540360 Sewer-Offset"].raw["_section"] == "Expense"
    assert by_label["412130 RV Monthly"].raw["_seller_line"] == "412130 RV Monthly"


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


async def _acquisition(session: AsyncSession) -> str:
    acquisition_id = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Acquisition(
            acquisition_id=acquisition_id,
            name="Ingestion Test Park",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
        )
    )
    await session.flush()
    return acquisition_id


async def test_ingest_pnl_loads_unmapped_with_raw_payload(session: AsyncSession) -> None:
    acquisition_id = await _acquisition(session)
    csv = b"Account,Amount\nSite Rental Income,2680000\nMarketing,96000\n"
    result = await ingest.ingest_document(
        session, acquisition_id, filename="pnl.csv", content_type="text/csv", data=csv
    )
    assert result.sheet_type == "pnl"
    assert result.financial_lines_loaded == 2

    lines = (
        (
            await session.execute(
                select(FinancialLine).where(FinancialLine.acquisition_id == acquisition_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(lines) == 2
    first = next(line_ for line_ in lines if line_.seller_source_line == "Site Rental Income")
    assert first.account_code is None  # loaded unmapped
    assert first.map_confidence == MapConfidence.UNMAPPED
    assert first.amount == Decimal("2680000")
    assert first.raw_payload == {"Account": "Site Rental Income", "Amount": "2680000"}  # provenance


async def test_ingest_quickbooks_recap_pnl(session: AsyncSession) -> None:
    acquisition_id = await _acquisition(session)
    result = await ingest.ingest_document(
        session, acquisition_id, filename="recap.csv", content_type="text/csv", data=_recap_csv()
    )
    assert result.sheet_type == "pnl"
    assert result.financial_lines_loaded == 3  # leaves only; subtotals/sections excluded

    lines = (
        (
            await session.execute(
                select(FinancialLine).where(FinancialLine.acquisition_id == acquisition_id)
            )
        )
        .scalars()
        .all()
    )
    monthly = next(line_ for line_ in lines if line_.seller_source_line == "412130 RV Monthly")
    assert monthly.account_code is None  # loaded unmapped for the GL engine
    assert monthly.map_confidence == MapConfidence.UNMAPPED
    assert monthly.amount == Decimal("217251.29")
    assert monthly.raw_payload["_section"] == "Income"  # provenance retained


async def test_reupload_versions_keep_history_and_switch_active(session: AsyncSession) -> None:
    from rjacq.ingestion import periods
    from rjacq.mapping.repository import list_lines

    acquisition_id = await _acquisition(session)
    v1 = b"Account,Amount\nSite Rental Income,2680000\n"
    v2 = b"Account,Amount\nSite Rental Income,2750000\nLaundry,4200\n"
    r1 = await ingest.ingest_document(
        session, acquisition_id, filename="pnl-2023.csv", content_type="text/csv", data=v1
    )
    r2 = await ingest.ingest_document(
        session, acquisition_id, filename="pnl-2024.csv", content_type="text/csv", data=v2
    )
    assert r1.period_id != r2.period_id  # each upload is its own dated version

    # Both versions are retained; exactly one is current (the newest), nothing deleted.
    versions = await periods.list_periods(session, acquisition_id)
    assert len(versions) == 2
    current = [p for p, _ in versions if p.is_current]
    assert len(current) == 1 and current[0].period_id == r2.period_id
    assert {p.source_filename for p, _ in versions} == {"pnl-2023.csv", "pnl-2024.csv"}

    # The GL view shows only the active version's lines (no bleed across versions).
    active_lines = await list_lines(session, acquisition_id)
    assert {line_.seller_source_line for line_ in active_lines} == {"Site Rental Income", "Laundry"}

    # Re-activating the older version switches the view back — and keeps the newer one on disk.
    ok = await periods.activate_period(session, acquisition_id, r1.period_id)
    assert ok
    active_lines = await list_lines(session, acquisition_id)
    assert {line_.seller_source_line for line_ in active_lines} == {"Site Rental Income"}
    assert len(await periods.list_periods(session, acquisition_id)) == 2  # nothing dropped

    # Activating a period from another acquisition is rejected (no cross-acquisition mutation).
    other = await _acquisition(session)
    assert await periods.activate_period(session, other, r1.period_id) is False


async def test_ingest_unit_mix_maps_known_skips_unknown(session: AsyncSession) -> None:
    acquisition_id = await _acquisition(session)
    csv = b"Unit Type,Count\nRV Pull-Through,96\nUFO Pad,3\n"
    result = await ingest.ingest_document(
        session, acquisition_id, filename="units.csv", content_type="text/csv", data=csv
    )
    assert result.sheet_type == "unit_mix"
    assert result.units_loaded == 1  # RV Pull-Through mapped
    assert result.units_skipped == 1  # UFO Pad unknown — skipped, not failed
    units = (
        (await session.execute(select(Unit).where(Unit.acquisition_id == acquisition_id)))
        .scalars()
        .all()
    )
    assert len(units) == 1


async def test_ingest_pdf_without_extractor_raises(session: AsyncSession) -> None:
    acquisition_id = await _acquisition(session)
    with pytest.raises(IngestError) as ei:
        await ingest.ingest_document(
            session,
            acquisition_id,
            filename="acquisition.pdf",
            content_type="application/pdf",
            data=b"%PDF-1.4",
        )
    assert ei.value.code == "pdf_extractor_not_configured"


async def test_ingest_unknown_sheet_is_reported_not_failed(session: AsyncSession) -> None:
    acquisition_id = await _acquisition(session)
    result = await ingest.ingest_document(
        session,
        acquisition_id,
        filename="misc.csv",
        content_type="text/csv",
        data=b"Foo,Bar\n1,2\n",
    )
    assert result.sheet_type == "unknown"
    assert result.financial_lines_loaded == 0
    assert result.note is not None

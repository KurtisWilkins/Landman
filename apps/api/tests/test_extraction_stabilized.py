"""Extraction-first stabilized NOI: the pro forma pulls stabilized revenue/opex from the
GL-mapped P&L (NOI bridge) when they're not entered manually. Real Postgres."""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import AccountLevel, AcquisitionStatus, Phase, PropertyType
from rjacq.models.financials import FinancialLine, FinancialPeriod
from rjacq.models.reference import GLAccount
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ADMIN = {"Authorization": "Bearer dev admin"}


async def _seed_mapped_pnl(db_url: str, acquisition_id: str) -> None:
    """An acquisition with a price and a GL-mapped P&L: revenue 1,200,000, opex 500,000."""
    engine = create_async_engine(db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        s.add(
            Acquisition(
                acquisition_id=acquisition_id,
                name="PF Extract",
                property_type=PropertyType.RV_RESORT,
                current_phase=Phase.INITIAL_UW,
                status=AcquisitionStatus.ACTIVE,
                purchase_price=Decimal("10000000"),
            )
        )
        period_id = f"fp_{uuid.uuid4().hex[:12]}"
        s.add(
            FinancialPeriod(
                period_id=period_id,
                acquisition_id=acquisition_id,
                label="T12",
                granularity="t12",
                is_current=True,
            )
        )
        rev_code = f"rev{uuid.uuid4().hex[:6]}"
        exp_code = f"exp{uuid.uuid4().hex[:6]}"
        s.add(
            GLAccount(
                account_code=rev_code,
                level=AccountLevel.LEAF,
                name="Site revenue",
                section="Income",
                default_noi_placement="above",
                active=True,
            )
        )
        s.add(
            GLAccount(
                account_code=exp_code,
                level=AccountLevel.LEAF,
                name="Payroll",
                section="Expense",
                default_noi_placement="above",
                active=True,
            )
        )
        s.add(
            FinancialLine(
                line_id=f"fl_{uuid.uuid4().hex[:12]}",
                acquisition_id=acquisition_id,
                period_id=period_id,
                seller_source_line="Site revenue",
                amount=Decimal("1200000"),
                account_code=rev_code,
            )
        )
        s.add(
            FinancialLine(
                line_id=f"fl_{uuid.uuid4().hex[:12]}",
                acquisition_id=acquisition_id,
                period_id=period_id,
                seller_source_line="Payroll",
                amount=Decimal("500000"),
                account_code=exp_code,
            )
        )
        await s.commit()
    await engine.dispose()


def test_stabilized_noi_autofills_from_pnl(migrated_db: str, client: TestClient) -> None:
    acquisition_id = f"dl_{uuid.uuid4().hex[:12]}"
    asyncio.run(_seed_mapped_pnl(migrated_db, acquisition_id))

    # GET pre-fills stabilized revenue/opex from the GL-mapped P&L (NOI bridge).
    g = client.get(f"/acquisitions/{acquisition_id}/proforma-inputs", headers=ADMIN).json()
    assert float(g["stabilized_revenue"]) == 1200000.0
    assert float(g["stabilized_opex"]) == 500000.0

    # PUT only financing/exit/hold (no stabilized values) -> recompute pulls NOI from the P&L.
    pf = client.put(
        f"/acquisitions/{acquisition_id}/proforma-inputs",
        json={
            "exit_cap": "0.07",
            "ltv": "0.65",
            "loan_rate": "0.065",
            "amort_months": 360,
            "io_years": 0,
            "hold_years": 5,
        },
        headers=ADMIN,
    )
    assert pf.status_code == 200, pf.text
    body = pf.json()
    assert len(body["years"]) == 5
    # Year-1 NOI = 1,200,000 - 500,000 = 700,000 (sourced from the bridge, not entered).
    assert float(body["years"][0]["noi"]) == 700000.0

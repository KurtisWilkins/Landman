"""SHIELD tests (§5.4): read-only guard, baseline aggregation, drift, assumption seeding."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import AcquisitionStatus, Phase, PropertyType
from rjacq.models.underwriting import Assumption
from rjacq.shield import service as svc
from rjacq.shield.baseline import MetricSpec, aggregate_baselines, parse_metric_specs
from rjacq.shield.connector import (
    ShieldReadOnlyError,
    assert_read_only,
    build_shield_connector,
)
from rjacq.shield.jobs import sync_shield_baselines
from rjacq.shield.snapshot import detect_drift
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def _get_assumption(session: AsyncSession, acquisition_id: str, key: str) -> Assumption:
    row = (
        (
            await session.execute(
                select(Assumption).where(
                    Assumption.acquisition_id == acquisition_id, Assumption.key == key
                )
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    return row


# ── read-only guard (never write to SHIELD) ─────────────────────────────────


def test_read_only_allows_select_and_with() -> None:
    assert_read_only("SELECT * FROM portfolio")
    assert_read_only("  with t as (select 1) select * from t")


@pytest.mark.parametrize(
    "q",
    [
        "UPDATE portfolio SET x=1",
        "DELETE FROM portfolio",
        "INSERT INTO x VALUES (1)",
        "DROP TABLE x",
        "select 1; drop table x",
        "EXEC sp_who",
    ],
)
def test_read_only_rejects_writes(q: str) -> None:
    with pytest.raises(ShieldReadOnlyError):
        assert_read_only(q)


def test_connector_factory_none_when_unconfigured() -> None:
    # C-14 unset in the test environment → no connector (graceful, not a guess).
    assert build_shield_connector() is None


# ── baseline aggregation (C-15 from config) ─────────────────────────────────


def test_parse_metric_specs() -> None:
    specs = parse_metric_specs('[{"key":"opex_ratio","column":"opex_ratio","aggregation":"avg"}]')
    assert specs == [MetricSpec("opex_ratio", "opex_ratio", "opex_ratio", "avg")]
    assert parse_metric_specs(None) == []


def test_aggregate_baselines_avg_and_sum() -> None:
    rows = [{"occ": "0.60", "rev": 100}, {"occ": "0.70", "rev": 150}, {"occ": None, "rev": 50}]
    specs = [
        MetricSpec("stabilized_occupancy", "Occupancy", "occ", "avg"),
        MetricSpec("total_rev", "Revenue", "rev", "sum"),
    ]
    out = aggregate_baselines(rows, specs)
    assert out["stabilized_occupancy"] == Decimal("0.65")  # mean of 0.60, 0.70 (None skipped)
    assert out["total_rev"] == Decimal("300")


# ── schema drift ────────────────────────────────────────────────────────────


def test_detect_drift() -> None:
    stored = {"portfolio": ["id", "occ", "adr"], "old": ["x"]}
    current = {"portfolio": ["id", "occ", "revpau"], "new": ["y"]}
    drift = detect_drift(stored, current)
    assert "table removed: old" in drift
    assert "table added: new" in drift
    assert "column removed: portfolio.adr" in drift
    assert "column added: portfolio.revpau" in drift


# ── seeding (real Postgres; preserves overrides) ────────────────────────────


class FakeConnector:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetch_all(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from rjacq.shield.connector import assert_read_only

        assert_read_only(query)
        return self._rows

    def snapshot(self) -> dict[str, list[str]]:
        return {"portfolio": ["occ"]}


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _make_acquisition(session: AsyncSession) -> str:
    acquisition_id = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Acquisition(
            acquisition_id=acquisition_id,
            name="SHIELD Test Park",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
        )
    )
    await session.flush()
    return acquisition_id


async def test_sync_seeds_baselines_and_preserves_override(session: AsyncSession) -> None:
    acquisition_id = await _make_acquisition(session)
    specs = [MetricSpec("opex_ratio", "OpEx ratio", "opex_ratio", "avg", "portfolio_rv_t12")]
    conn = FakeConnector([{"opex_ratio": "0.48"}, {"opex_ratio": "0.50"}])

    baselines = await svc.sync_baselines(
        session,
        connector=conn,
        query="SELECT opex_ratio FROM portfolio",
        specs=specs,
        acquisition_ids=[acquisition_id],
    )
    await session.commit()
    assert baselines["opex_ratio"] == Decimal("0.49")

    a = await _get_assumption(session, acquisition_id, "opex_ratio")
    assert a.baseline_value == Decimal("0.49")
    assert a.shield_source == "portfolio_rv_t12"
    assert a.is_overridden is False

    # Operator overrides, then a later sync refreshes the baseline but keeps the override.
    a.override_value = Decimal("0.55")
    a.is_overridden = True
    a.overridden_by = "kurtis"
    await session.flush()

    conn2 = FakeConnector([{"opex_ratio": "0.52"}])
    await svc.sync_baselines(
        session,
        connector=conn2,
        query="SELECT opex_ratio FROM portfolio",
        specs=specs,
        acquisition_ids=[acquisition_id],
    )
    await session.commit()
    a2 = await _get_assumption(session, acquisition_id, "opex_ratio")
    assert a2.baseline_value == Decimal("0.52")  # baseline refreshed
    assert a2.override_value == Decimal("0.55")  # override preserved (provenance)
    assert a2.is_overridden is True


async def test_sync_job_skips_when_unconfigured() -> None:
    result = await sync_shield_baselines({})
    assert "skipped" in result  # C-14 unset

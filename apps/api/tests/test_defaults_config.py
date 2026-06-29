"""Global default-rules config (real Postgres): seed/list, the RULE_LIBRARY fallback, and a global
edit flowing through to a budget default."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import AccountLevel, AcquisitionStatus, Phase, PropertyType
from rjacq.models.reference import GLAccount
from rjacq.underwriting import budget_service, defaults_config
from rjacq.underwriting.defaults_rules import RULE_LIBRARY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _account(session: AsyncSession, code: str, section: str) -> None:
    session.add(
        GLAccount(
            account_code=code,
            level=AccountLevel.LEAF,
            name=f"Acct {code}",
            section=section,
            default_noi_placement="above",
            active=True,
        )
    )
    await session.flush()


async def _acquisition(session: AsyncSession) -> str:
    aid = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Acquisition(
            acquisition_id=aid,
            name="Config Test",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
        )
    )
    await session.flush()
    return aid


async def test_effective_rules_fall_back_to_library_when_unseeded(session: AsyncSession) -> None:
    rules = await defaults_config.effective_rules(session)
    assert len(rules) == len(RULE_LIBRARY)


async def test_list_seeds_then_returns_all(session: AsyncSession) -> None:
    rows = await defaults_config.list_rules(session)
    assert {r.rule_key for r in rows} == {r.rule_key for r in RULE_LIBRARY}
    # idempotent — listing again doesn't duplicate
    again = await defaults_config.list_rules(session)
    assert len(again) == len(rows)


async def test_update_rule_changes_effective(session: AsyncSession) -> None:
    await defaults_config.update_rule(session, "shield", value=Decimal("2000"), actor="kurtis")
    rules = {r.rule_key: r for r in await defaults_config.effective_rules(session)}
    assert rules["shield"].value == Decimal("2000")


async def test_global_edit_flows_into_budget_default(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    await _account(session, "600410", "Expense")
    # Globally bump Shield to $2,000/mo, then seed → the budget default reflects it.
    await defaults_config.update_rule(session, "shield", value=Decimal("2000"), actor="kurtis")
    doc = await budget_service.seed_budget(session, aid)
    row = next(r for r in doc.rows if r.account_code == "600410")
    assert row.year1_annual == Decimal("24000")  # 2,000/mo × 12


async def test_disable_rule_skips_it_in_budget(session: AsyncSession) -> None:
    aid = await _acquisition(session)
    await _account(session, "600410", "Expense")
    await defaults_config.update_rule(session, "shield", enabled=False, actor="kurtis")
    doc = await budget_service.seed_budget(session, aid)
    assert not any(r.account_code == "600410" for r in doc.rows)

"""Normalized load routine (design doc §5.2 / §8). All ingest paths converge here.

Financial lines load **unmapped** (account_code null) for the GL mapping engine to propose
against later; the original row is retained in ``raw_payload`` (provenance). Unit-mix rows
map to the §8.2 unit_type vocabulary; unknown types are skipped (greedy, never fails).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MapConfidence, UnitType
from ..models.financials import FinancialLine, FinancialPeriod
from ..models.property import Unit
from .records import ParsedLine, ParsedUnit

_UNIT_SYNONYMS: dict[str, UnitType] = {
    "rv pull-through": UnitType.RV_PULL_THROUGH,
    "pull-through": UnitType.RV_PULL_THROUGH,
    "pull through": UnitType.RV_PULL_THROUGH,
    "rv back-in": UnitType.RV_BACK_IN,
    "back-in": UnitType.RV_BACK_IN,
    "back in": UnitType.RV_BACK_IN,
    "cabin": UnitType.CABIN,
    "park model": UnitType.PARK_MODEL,
    "tent": UnitType.TENT,
    "glamping": UnitType.GLAMPING,
    "marina slip": UnitType.MARINA_SLIP,
    "slip": UnitType.MARINA_SLIP,
    "rv storage": UnitType.RV_STORAGE,
    "storage": UnitType.RV_STORAGE,
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _match_unit_type(label: str) -> UnitType | None:
    key = label.strip().lower()
    if key in _UNIT_SYNONYMS:
        return _UNIT_SYNONYMS[key]
    for syn, ut in _UNIT_SYNONYMS.items():
        if syn in key:
            return ut
    return None


async def load_pnl(
    session: AsyncSession,
    deal_id: str,
    *,
    period_label: str,
    lines: Sequence[ParsedLine],
    source_filename: str | None = None,
) -> tuple[str, int]:
    """Create a financial period and load lines unmapped with raw_payload retained.

    Each upload is a new, dated version: prior versions for the deal are demoted to
    ``is_current=False`` (retained, never deleted) and the new one becomes current (§5.2,
    append-never-overwrite). An operator can re-activate an older version later.
    """
    # Demote any existing current version for this deal — an UPDATE, not a delete (history kept).
    await session.execute(
        update(FinancialPeriod)
        .where(FinancialPeriod.deal_id == deal_id, FinancialPeriod.is_current.is_(True))
        .values(is_current=False)
    )
    period_id = _new_id("fp")
    session.add(
        FinancialPeriod(
            period_id=period_id,
            deal_id=deal_id,
            label=period_label,
            granularity="t12",
            source_filename=source_filename,
            is_current=True,
        )
    )
    await session.flush()  # ensure the period exists before its lines reference it (FK)
    for line in lines:
        session.add(
            FinancialLine(
                line_id=_new_id("fl"),
                deal_id=deal_id,
                period_id=period_id,
                account_code=None,  # unmapped — mapping engine proposes later (§5.3)
                map_confidence=MapConfidence.UNMAPPED,
                seller_source_line=line.seller_source_line,
                amount=line.amount,
                is_addback=False,
                raw_payload=line.raw,
            )
        )
    await session.flush()
    return period_id, len(lines)


async def load_units(
    session: AsyncSession, deal_id: str, units: Sequence[ParsedUnit]
) -> tuple[int, int]:
    """Load unit-mix rows; returns (loaded, skipped_unknown_types)."""
    loaded = skipped = 0
    for u in units:
        ut = _match_unit_type(u.unit_type)
        if ut is None:
            skipped += 1
            continue
        session.add(Unit(unit_id=_new_id("un"), deal_id=deal_id, unit_type=ut, count=u.count))
        loaded += 1
    await session.flush()
    return loaded, skipped

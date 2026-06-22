"""Global underwriting defaults that seed each acquisition's pro-forma inputs.

A singleton row (``underwriting_defaults``) holds admin-set values; any null field falls back to
the BUILT_IN best-guess below. These are best-guess starting points, editable by an admin in
Settings — never silently baked into business logic (CLAUDE.md rule #2): the engine still reads
each acquisition's own saved inputs; these only pre-fill the form for a new acquisition.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.underwriting import UnderwritingDefaults as DefaultsRow

_SINGLETON = "default"

# Best-guess starting defaults (admin-configurable in Settings).
BUILT_IN: dict[str, Decimal | int] = {
    "ltv": Decimal("0.65"),
    "loan_rate": Decimal("0.065"),
    "noi_growth": Decimal("0.03"),
    "exit_cap": Decimal("0.07"),
    "selling_cost_rate": Decimal("0.02"),
    "capex_reserve_rate": Decimal("0"),
    "amort_months": 360,
    "io_years": 0,
    "hold_years": 5,
    # Org-wide JV terms (seed an acquisition's promote inputs; per-deal overrides win).
    "rjourney_coinvest_pct": Decimal("0.10"),
    "acquisition_fee_pct": Decimal("0"),
    "mgmt_fee_pct": Decimal("0"),
}
_FIELDS = tuple(BUILT_IN.keys())


async def get_effective(session: AsyncSession) -> dict[str, Decimal | int]:
    """The effective defaults: the admin-set value per field, else the built-in best-guess."""
    row = await session.get(DefaultsRow, _SINGLETON)
    return {
        field: (
            getattr(row, field)
            if row is not None and getattr(row, field) is not None
            else BUILT_IN[field]
        )
        for field in _FIELDS
    }


async def set_defaults(session: AsyncSession, fields: dict[str, Any]) -> dict[str, Decimal | int]:
    """Upsert admin-set defaults (only provided fields), commit, and return the effective set."""
    row = await session.get(DefaultsRow, _SINGLETON)
    if row is None:
        row = DefaultsRow(id=_SINGLETON)
        session.add(row)
    for key, value in fields.items():
        if key in _FIELDS:
            setattr(row, key, value)
    await session.commit()
    return await get_effective(session)

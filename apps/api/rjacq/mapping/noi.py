"""NOI bridge over a acquisition's mapped financial lines (design doc §5.3.7).

Reuses the pure ``underwriting.engine.normalized_noi``: above-the-line revenue minus
above-the-line operating expense, excluding below-the-line (700000) / non-operating (800000)
and adding back detected owner/one-time items. Unmapped lines are not yet in NOI (they are
surfaced for review and never silently dropped).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..underwriting.engine import NoiBridge, NoiLine, normalized_noi
from . import repository as repo


async def noi_bridge_for_acquisition(session: AsyncSession, acquisition_id: str) -> NoiBridge:
    lines = await repo.list_lines(session, acquisition_id)
    noi_lines: list[NoiLine] = []
    for line in lines:
        if line.account_code is None:
            continue  # unmapped — not in NOI yet (surfaced for review)
        account = await repo.get_account(session, line.account_code)
        is_expense = bool(account and account.section == "Expense")
        placement = (
            line.noi_placement.value
            if line.noi_placement is not None
            else (account.default_noi_placement if account else "above")
        ) or "above"
        noi_lines.append(
            NoiLine(
                amount=line.amount or Decimal(0),
                noi_placement=placement,
                is_expense=is_expense,
                is_addback=bool(line.is_addback),
            )
        )
    return normalized_noi(noi_lines)

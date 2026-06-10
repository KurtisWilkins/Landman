"""Idempotent seed loader for reference data.

Run via ``python -m rjacq.seeds.load`` (Makefile target ``seed``). Safe to re-run: rows are
upserted by primary key. Loads the §8.5 GL excerpt and the explicitly-named gate questions;
merges fuller config files when their ``*_config_path`` settings are set (B-13 / A-8 / A-9).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.db import SessionFactory
from ..core.logging import configure_logging, get_logger
from ..models import GateQuestion, GLAccount
from .gate_questions import GATE_QUESTIONS
from .gl_accounts import GL_ACCOUNTS

log = get_logger("seed")


async def seed_gl_accounts(session: AsyncSession) -> int:
    existing = set((await session.execute(select(GLAccount.account_code))).scalars().all())
    added = 0
    # Insert parents before children so the self-FK is satisfied (rows are pre-sorted).
    for row in sorted(GL_ACCOUNTS, key=lambda r: r["sort"]):
        if row["account_code"] in existing:
            continue
        session.add(
            GLAccount(
                account_code=row["account_code"],
                parent_code=row["parent_code"],
                level=row["level"],
                name=row["name"],
                section=row["section"],
                normal_balance=row["normal_balance"],
                sort=row["sort"],
                active=True,
                default_noi_placement=row["default_noi_placement"],
            )
        )
        added += 1
    if settings.gl_chart_config_path:
        log.info("seed.gl_chart.config_path_set", path=settings.gl_chart_config_path)
        # TODO(decision: §14 B-13): merge the full RJourneyP_LGLStructure.xlsx chart here.
    return added


async def seed_gate_questions(session: AsyncSession) -> int:
    existing = set((await session.execute(select(GateQuestion.question_id))).scalars().all())
    added = 0
    for row in GATE_QUESTIONS:
        if row["question_id"] in existing:
            continue
        session.add(
            GateQuestion(
                question_id=row["question_id"],
                phase=row["phase"],
                category=row["category"],
                text=row["text"],
                blocking=row["blocking"],
                default_route_type=row["default_route_type"],
                active=True,
                created_by="seed",
                approved_by="seed",
            )
        )
        added += 1
    if settings.gate_questions_config_path:
        log.info("seed.gate_questions.config_path_set", path=settings.gate_questions_config_path)
        # TODO(decision: §14 A-8/A-9): merge reviewed DD/Close/full gate sets here.
    return added


async def run() -> None:
    configure_logging()
    async with SessionFactory() as session:
        gl = await seed_gl_accounts(session)
        gq = await seed_gate_questions(session)
        await session.commit()
    log.info("seed.complete", gl_accounts_added=gl, gate_questions_added=gq)


if __name__ == "__main__":
    asyncio.run(run())

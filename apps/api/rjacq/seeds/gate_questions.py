"""Gate-question seeds.

Only the items the design doc names *explicitly* are seeded here (§5.7): the Initial UW
set (P&L + unit mix) and the LOI set (attorneys looped, acquisition points). These are structural,
not guessed business values.

The full sets are unresolved decisions and are NOT invented here:
  • The RV-remastered Due Diligence checklist (50+ items, which are blocking) — §14 A-8.
  • Final Initial UW / LOI content and the Close set — §14 A-9.
The loader merges a reviewed config file when ``gate_questions_config_path`` is set. Until
then DD/Close intentionally seed empty so nothing un-vetted gates a acquisition.

``blocking`` defaults to False for any item whose blocking status is itself part of the
open decision; the explicitly-named "must have P&L / unit mix / executed LOI" items are
marked blocking because the doc states a acquisition cannot clear Initial UW without them.
"""

from __future__ import annotations

from typing import TypedDict


class GateQuestionRow(TypedDict):
    question_id: str
    phase: str
    category: str
    text: str
    blocking: bool
    default_route_type: str | None


GATE_QUESTIONS: list[GateQuestionRow] = [
    # ── Initial UW (§5.7: "P&L + unit mix") ─────────────────────────────
    {
        "question_id": "q_iuw_pnl",
        "phase": "initial_uw",
        "category": "financial",
        "text": "Seller P&L (T12 or annual) received and mapped.",
        "blocking": True,
        "default_route_type": "internal",
    },
    {
        "question_id": "q_iuw_unit_mix",
        "phase": "initial_uw",
        "category": "property",
        "text": "Unit mix (site count by type, hookups, amperage) received.",
        "blocking": True,
        "default_route_type": "internal",
    },
    # ── LOI (§5.7: "attorneys looped, acquisition points") ─────────────────────
    {
        "question_id": "q_loi_attorneys",
        "phase": "loi",
        "category": "legal",
        "text": "Attorneys looped in on the LOI.",
        "blocking": True,
        "default_route_type": "external",
    },
    {
        "question_id": "q_loi_deal_points",
        "phase": "loi",
        "category": "acquisition",
        "text": "Key acquisition points (price, terms, contingencies) agreed.",
        "blocking": True,
        "default_route_type": "internal",
    },
    # Due Diligence + Close sets load from gate_questions_config_path — see A-8 / A-9.
]

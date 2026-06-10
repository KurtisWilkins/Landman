"""GL chart seed — the design doc §8.5 excerpt.

This is the published excerpt only. The full ~235-line chart seeds from
``RJourneyP_LGLStructure.xlsx`` once that file is confirmed as the current, complete chart
and its owner is named — TODO(decision: §14 B-13). The loader merges that file when the
``gl_chart_config_path`` setting points at it; until then this excerpt is authoritative for
local/dev and CI.

Each row: (account_code, parent_code, level, name, section, normal_balance, sort,
default_noi_placement). ``default_noi_placement`` travels with the account so a 700000 line
is auto-treated below the line and 800000 as non-operating during normalization (§8.5).
"""

from __future__ import annotations

from typing import TypedDict


class GLRow(TypedDict):
    account_code: str
    parent_code: str | None
    level: str
    name: str
    section: str
    normal_balance: str
    sort: int
    default_noi_placement: str


GL_ACCOUNTS: list[GLRow] = [
    # ── Income ──────────────────────────────────────────────────────────
    {
        "account_code": "400000",
        "parent_code": None,
        "level": "major_group",
        "name": "Revenue",
        "section": "Income",
        "normal_balance": "credit",
        "sort": 100,
        "default_noi_placement": "above",
    },
    {
        "account_code": "400100",
        "parent_code": "400000",
        "level": "subgroup",
        "name": "Campground Rent",
        "section": "Income",
        "normal_balance": "credit",
        "sort": 110,
        "default_noi_placement": "above",
    },
    {
        "account_code": "400105",
        "parent_code": "400100",
        "level": "leaf",
        "name": "RV Short Term",
        "section": "Income",
        "normal_balance": "credit",
        "sort": 111,
        "default_noi_placement": "above",
    },
    {
        "account_code": "400110",
        "parent_code": "400100",
        "level": "leaf",
        "name": "RV Extended Stay",
        "section": "Income",
        "normal_balance": "credit",
        "sort": 112,
        "default_noi_placement": "above",
    },
    {
        "account_code": "400115",
        "parent_code": "400100",
        "level": "leaf",
        "name": "Lodging Short Term",
        "section": "Income",
        "normal_balance": "credit",
        "sort": 113,
        "default_noi_placement": "above",
    },
    {
        "account_code": "400120",
        "parent_code": "400100",
        "level": "leaf",
        "name": "Tent",
        "section": "Income",
        "normal_balance": "credit",
        "sort": 114,
        "default_noi_placement": "above",
    },
    {
        "account_code": "400200",
        "parent_code": "400000",
        "level": "subgroup",
        "name": "Self Storage Rent",
        "section": "Income",
        "normal_balance": "credit",
        "sort": 120,
        "default_noi_placement": "above",
    },
    {
        "account_code": "401000",
        "parent_code": "400000",
        "level": "subgroup",
        "name": "Online Travel Agencies",
        "section": "Income",
        "normal_balance": "credit",
        "sort": 130,
        "default_noi_placement": "above",
    },
    {
        "account_code": "402000",
        "parent_code": "400000",
        "level": "subgroup",
        "name": "Marina Revenue",
        "section": "Income",
        "normal_balance": "credit",
        "sort": 140,
        "default_noi_placement": "above",
    },
    {
        "account_code": "403000",
        "parent_code": "400000",
        "level": "subgroup",
        "name": "Ancillary Revenue",
        "section": "Income",
        "normal_balance": "credit",
        "sort": 150,
        "default_noi_placement": "above",
    },
    {
        "account_code": "404000",
        "parent_code": "400000",
        "level": "subgroup",
        "name": "Retail Sales",
        "section": "Income",
        "normal_balance": "credit",
        "sort": 160,
        "default_noi_placement": "above",
    },
    # ── Expense ─────────────────────────────────────────────────────────
    {
        "account_code": "600200",
        "parent_code": None,
        "level": "subgroup",
        "name": "Advertising & Promotion",
        "section": "Expense",
        "normal_balance": "debit",
        "sort": 200,
        "default_noi_placement": "above",
    },
    {
        "account_code": "605100",
        "parent_code": None,
        "level": "subgroup",
        "name": "Repairs & Maintenance",
        "section": "Expense",
        "normal_balance": "debit",
        "sort": 210,
        "default_noi_placement": "above",
    },
    {
        "account_code": "605400",
        "parent_code": None,
        "level": "subgroup",
        "name": "Utilities",
        "section": "Expense",
        "normal_balance": "debit",
        "sort": 220,
        "default_noi_placement": "above",
    },
    {
        "account_code": "605410",
        "parent_code": "605400",
        "level": "leaf",
        "name": "Electric",
        "section": "Expense",
        "normal_balance": "debit",
        "sort": 221,
        "default_noi_placement": "above",
    },
    {
        "account_code": "605450",
        "parent_code": "605400",
        "level": "leaf",
        "name": "Water-Well Testing & Permits",
        "section": "Expense",
        "normal_balance": "debit",
        "sort": 222,
        "default_noi_placement": "above",
    },
    {
        "account_code": "605455",
        "parent_code": "605400",
        "level": "leaf",
        "name": "Water & Sewer",
        "section": "Expense",
        "normal_balance": "debit",
        "sort": 223,
        "default_noi_placement": "above",
    },
    {
        "account_code": "605460",
        "parent_code": "605400",
        "level": "leaf",
        "name": "Septic Pumping & Treatment",
        "section": "Expense",
        "normal_balance": "debit",
        "sort": 224,
        "default_noi_placement": "above",
    },
    # Below-the-line groups (excluded from normalized NOI).
    {
        "account_code": "700000",
        "parent_code": None,
        "level": "subgroup",
        "name": "Debt Service Interest",
        "section": "Expense",
        "normal_balance": "debit",
        "sort": 700,
        "default_noi_placement": "below",
    },
    {
        "account_code": "800000",
        "parent_code": None,
        "level": "subgroup",
        "name": "Non-Operational Expenses",
        "section": "Expense",
        "normal_balance": "debit",
        "sort": 800,
        "default_noi_placement": "non_operating",
    },
]

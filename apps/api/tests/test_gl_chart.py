"""The seeded RJourney GL chart (§8.5) — pure checks over GL_ACCOUNTS (no DB)."""

from __future__ import annotations

from rjacq.seeds.gl_accounts import GL_ACCOUNTS


def test_chart_is_well_formed() -> None:
    codes = [r["account_code"] for r in GL_ACCOUNTS]
    assert len(codes) == len(set(codes))  # account_code is the PK — no duplicates
    assert len(codes) > 150
    code_set = set(codes)
    for r in GL_ACCOUNTS:
        assert r["parent_code"] is None or r["parent_code"] in code_set  # parents resolvable


def test_defaults_target_accounts_exist() -> None:
    code_set = {r["account_code"] for r in GL_ACCOUNTS}
    # Shield (600410), website (600210), secondary marketing (601010), PPC (600225).
    assert {"600410", "600210", "601010", "600225"} <= code_set


def test_noi_placement_by_range() -> None:
    by = {r["account_code"]: r for r in GL_ACCOUNTS}
    assert by["700000"]["default_noi_placement"] == "below"  # debt service
    assert by["800000"]["default_noi_placement"] == "non_operating"
    assert by["600225"]["default_noi_placement"] == "above" and by["600225"]["section"] == "Expense"
    assert by["400105"]["default_noi_placement"] == "above" and by["400105"]["section"] == "Income"


def test_seed_entry_point_target_exists() -> None:
    # The `rjacq-seed` console script (the Container Apps seed job) points at this callable.
    from rjacq.seeds.load import main

    assert callable(main)

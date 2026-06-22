"""Budget defaults engine tests (§5.5 Part 3): pure, decision-free formulas with worked examples.

Numbers are config (passed via the context); these pin the formula shapes (Shield fixed, two
marketing lines, the two-line PPC) and the graceful no-op when a rule isn't configured yet."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rjacq.underwriting.budget_defaults import (
    DefaultsContext,
    all_defaults,
    ppc_defaults,
    shield_default,
)


def _ctx(**overrides: Any) -> DefaultsContext:
    base: dict[str, Any] = {
        "site_count": None,
        "shield_monthly": Decimal("1000"),
        "shield_account_code": None,
        "mktg_website_monthly": Decimal("825"),
        "mktg_website_account_code": None,
        "mktg_secondary_monthly": Decimal("850"),
        "mktg_secondary_account_code": None,
        "ppc_rate": None,
        "ppc_target_volume": None,
        "ppc_intercompany_pct": None,
        "ppc_google_account_code": None,
        "ppc_intercompany_account_code": None,
    }
    base.update(overrides)
    return DefaultsContext(**base)


def test_shield_is_fixed_and_overrides() -> None:
    dl = shield_default(_ctx(shield_account_code="6000"))
    assert dl is not None
    assert dl.monthly_amount == Decimal("1000")
    assert dl.default_rule_key == "shield_fixed"
    assert dl.overrides_actuals is True  # ignores historical Shield charges


def test_shield_none_until_configured() -> None:
    assert shield_default(_ctx()) is None


def test_marketing_two_independent_lines() -> None:
    lines = all_defaults(_ctx(mktg_website_account_code="5000", mktg_secondary_account_code="5001"))
    amounts = {line.default_rule_key: line.monthly_amount for line in lines}
    assert amounts == {"mktg_website": Decimal("825"), "mktg_secondary": Decimal("850")}


def test_ppc_two_line_linear_formula() -> None:
    lines = ppc_defaults(
        _ctx(
            site_count=12,
            ppc_rate=Decimal("3.5"),
            ppc_target_volume=Decimal("4"),
            ppc_intercompany_pct=Decimal("0.15"),
            ppc_google_account_code="7000",
            ppc_intercompany_account_code="7001",
        )
    )
    assert len(lines) == 2
    google, intercompany = lines
    assert google.monthly_amount == Decimal("168")  # 12 sites × 4 vol × $3.5
    assert intercompany.monthly_amount == Decimal("25.20")  # 168 × 15%
    assert google.default_rule_key == "ppc_google"
    assert intercompany.default_rule_key == "ppc_intercompany"


def test_ppc_combined_when_same_account() -> None:
    # Both components post to the same Pay-Per-Click GL → one combined line (google + intercompany).
    lines = ppc_defaults(
        _ctx(
            site_count=12,
            ppc_rate=Decimal("3.5"),
            ppc_target_volume=Decimal("4"),
            ppc_intercompany_pct=Decimal("0.15"),
            ppc_google_account_code="600225",
            ppc_intercompany_account_code="600225",
        )
    )
    assert len(lines) == 1
    assert lines[0].account_code == "600225"
    assert lines[0].default_rule_key == "ppc"
    assert lines[0].monthly_amount == Decimal("193.20")  # 168 + 25.20


def test_ppc_empty_until_fully_configured() -> None:
    # site_count + an account code present, but no rate/volume/% → no fabricated number.
    assert ppc_defaults(_ctx(site_count=12, ppc_google_account_code="7000")) == []


def test_all_defaults_empty_when_unconfigured() -> None:
    assert all_defaults(_ctx()) == []  # the engine no-ops until codes + rates are set

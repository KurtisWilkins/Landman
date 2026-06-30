"""Hierarchical GL roll-up (canonical chart: section → group → sub-group → detail).

Pure worked examples, no DB. The headline case pins a real slice of the RJourney consolidated
income statement (``Consolidated-T-12``) so the engine provably reproduces the source's own
``Total - …`` rows — including the two negative contra recoveries inside Utilities.
"""

from __future__ import annotations

from decimal import Decimal

from rjacq.underwriting.budget import TreeNode, roll_up_tree

_D = Decimal


def test_utilities_group_nets_contra_recoveries() -> None:
    """605400 Utilities = sum of its 13 leaves, with 605415 Utility Recovery and 605465 Water &
    Sewer Recovery carried as NEGATIVE offsets. Matches the workbook's Total - 605400 = 1,713,517.19
    (Electric 1,873,402.28 − Utility Recovery 1,087,205.20 is the 62% bill-back basis)."""
    leaves = {
        "605405": _D("327419.14"),  # Disposal
        "605410": _D("1873402.28"),  # Electric
        "605415": _D("-1087205.20"),  # Utility Recovery (contra)
        "605420": _D("60166.97"),  # Natural Gas
        "605425": _D("79071.81"),  # Propane
        "605430": _D("110355.15"),  # Internet
        "605435": _D("7484.27"),  # Satellite
        "605440": _D("11696.58"),  # Telephone
        "605445": _D("51847.43"),  # Cell Phone
        "605450": _D("90458.10"),  # Water-Well Testing
        "605455": _D("486945.47"),  # Water & Sewer
        "605460": _D("31530.46"),  # Septic
        "605465": _D("-329655.27"),  # Water & Sewer Recovery (contra)
    }
    # chart: 605400 Utilities (sub-group) under 605000 O&M (group) under the Expense section.
    nodes = [
        TreeNode("605000", None, "Expense", "above"),
        TreeNode("605400", "605000", "Expense", "above"),
        *[TreeNode(c, "605400", "Expense", "above") for c in leaves],
    ]
    amounts = {c: (v, v) for c, v in leaves.items()}  # same value both columns for the example
    out = roll_up_tree(nodes, amounts)

    assert out.subtotals["605400"] == (_D("1713517.19"), _D("1713517.19"))
    # the group total rolls up into its parent O&M group unchanged (only child here)
    assert out.subtotals["605000"] == (_D("1713517.19"), _D("1713517.19"))
    # the contra leaf keeps its negative sign (a recovery, not a positive expense)
    assert out.subtotals["605415"] == (_D("-1087205.20"), _D("-1087205.20"))


def test_noi_is_income_minus_expense_with_contra_income() -> None:
    """NOI = Total Income − Total Expense. A contra-income line (e.g. Discounts) is negative and so
    reduces revenue; COGS sits in the Expense section and counts against NOI."""
    nodes = [
        TreeNode("400000", None, "Income", "above"),
        TreeNode("400100", "400000", "Income", "above"),
        TreeNode("421000", "400000", "Income", "above"),  # Discounts (contra income)
        TreeNode("500000", None, "Expense", "above"),  # COGS folds into Expense
        TreeNode("605000", None, "Expense", "above"),
    ]
    amounts = {
        "400100": (_D("1000"), _D("1100")),
        "421000": (_D("-150"), _D("-120")),  # contra income, negative
        "500000": (_D("80"), _D("90")),
        "605000": (_D("300"), _D("330")),
    }
    out = roll_up_tree(nodes, amounts)
    assert out.prior_revenue == _D("850") and out.year1_revenue == _D("980")  # 1000 − 150
    assert out.prior_expense == _D("380") and out.year1_expense == _D("420")  # 80 + 300
    assert out.prior_noi == _D("470") and out.year1_noi == _D("560")
    # the revenue group nets the discount: 1000 − 150 = 850
    assert out.subtotals["400000"] == (_D("850"), _D("980"))


def test_below_the_line_excluded_from_noi_but_still_subtotaled() -> None:
    """A below-the-line / non-operating node (debt service, CapEx) rolls up for display but does
    NOT count toward operating NOI."""
    nodes = [
        TreeNode("400000", None, "Income", "above"),
        TreeNode("700000", None, "Expense", "below"),  # debt service interest
        TreeNode("800000", None, "Expense", "non_operating"),  # CapEx / non-op
    ]
    amounts = {
        "400000": (_D("1000"), _D("1000")),
        "700000": (_D("400"), _D("400")),
        "800000": (_D("50"), _D("50")),
    }
    out = roll_up_tree(nodes, amounts)
    assert out.prior_expense == _D("0")  # neither below nor non-op counts as operating expense
    assert out.prior_noi == _D("1000")  # NOI ignores debt service + CapEx
    assert out.subtotals["700000"] == (_D("400"), _D("400"))  # still subtotaled for the grid


def test_empty_chart_and_unknown_amount_codes() -> None:
    """No nodes → zeros; an amount for a code absent from the chart is ignored for subtotals but
    still classified for NOI only if the chart knows its section (here it doesn't → ignored)."""
    out = roll_up_tree([], {"999999": (_D("5"), _D("5"))})
    assert out.prior_noi == _D("0") and out.subtotals == {}

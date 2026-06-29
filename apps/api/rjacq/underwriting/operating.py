"""Pure operational-input math (defaults engine, Part 1).

The defaults engine needs a few per-property *drivers* — billable unit counts, the electric
expense, and employee headcount — captured per acquisition and editable. This module holds the
pure, DB-free logic the engine and the API both rely on, so it's unit-tested like the pro-forma /
promote / budget engines.

Billable units are the per-unit Repairs & Maintenance driver: **RV pads + cabins + glamping**,
with **tents excluded** (a tent site isn't a billable unit). The category list is *not* hardcoded
to those three — a property can add finer sub-types (e.g. "RV pads — pull-through") and each unit
group carries its own ``billable`` flag, so the driver is just "sum the counts of the billable
groups". A billable group with no count yet is a "needs input" gap: the dependent default can't
compute against a guessed number (CLAUDE.md rule #2), so we surface the gap rather than fill it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# Categories that count toward the per-unit drivers by default. Tents are intentionally absent —
# they seed with ``billable=False``. New/custom groups default to billable; the user can toggle.
DEFAULT_BILLABLE_CATEGORIES: frozenset[str] = frozenset({"rv_pad", "cabin", "glamping"})

# Seed mapping from the §8.2 ``UnitType`` vocabulary to a billable-unit category. Types absent
# here (marina slips, RV storage) seed as non-billable so they never inflate the R&M driver.
UNIT_TYPE_TO_CATEGORY: dict[str, str] = {
    "rv_pull_through": "rv_pad",
    "rv_back_in": "rv_pad",
    "cabin": "cabin",
    "park_model": "cabin",
    "glamping": "glamping",
    "tent": "tent",
}


@dataclass(frozen=True)
class UnitGroupInput:
    """A unit grouping for the driver math: its category, count (None = not captured), and whether
    it counts toward the billable-unit drivers."""

    category: str
    count: int | None
    billable: bool


def billable_unit_total(groups: Sequence[UnitGroupInput]) -> int:
    """Total billable units across the groups (RV pads + cabins + glamping by default; tents
    excluded). Sums only the groups that are both ``billable`` and have a captured count, so it's
    always a concrete number — pair with :func:`units_need_input` to know if it's complete."""
    return sum(g.count for g in groups if g.billable and g.count is not None)


def units_need_input(groups: Sequence[UnitGroupInput]) -> bool:
    """True when the billable-unit driver is incomplete: no billable group exists, or a billable
    group is missing its count. Drives the "needs input" prompt — the per-unit defaults can't be
    trusted until this is False."""
    billable = [g for g in groups if g.billable]
    if not billable:
        return True
    return any(g.count is None for g in billable)


def default_billable(category: str) -> bool:
    """Whether a category counts toward the billable drivers by default (user-overridable)."""
    return category in DEFAULT_BILLABLE_CATEGORIES

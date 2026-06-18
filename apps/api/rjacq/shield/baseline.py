"""Baseline-metric aggregation (design doc §5.4).

Which metrics to pull and how to aggregate them is an unresolved decision (§14 C-15); the
``MetricSpec`` list is parsed from config (JSON), never hard-coded. The aggregation itself is
a pure, tested function over the rows the connector returns.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class MetricSpec:
    """A baseline metric to derive from SHIELD portfolio actuals.

    ``column`` is the source field on each row; ``aggregation`` ∈ {avg, sum, min, max}.
    ``key``/``label`` map onto a acquisition assumption.
    """

    key: str
    label: str
    column: str
    aggregation: str
    shield_source: str = "shield"


def parse_metric_specs(config_json: str | None) -> list[MetricSpec]:
    """Parse the C-15 metric spec list from config JSON. Empty when unconfigured."""
    if not config_json:
        return []
    raw = json.loads(config_json)
    return [
        MetricSpec(
            key=item["key"],
            label=item.get("label", item["key"]),
            column=item["column"],
            aggregation=item.get("aggregation", "avg"),
            shield_source=item.get("shield_source", "shield"),
        )
        for item in raw
    ]


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def aggregate_baselines(
    rows: Sequence[dict[str, Any]], specs: Sequence[MetricSpec]
) -> dict[str, Decimal]:
    """Aggregate portfolio rows into baseline values per spec. Skips metrics with no data."""
    out: dict[str, Decimal] = {}
    for spec in specs:
        values = [d for r in rows if (d := _to_decimal(r.get(spec.column))) is not None]
        if not values:
            continue
        if spec.aggregation == "sum":
            out[spec.key] = sum(values, Decimal(0))
        elif spec.aggregation == "min":
            out[spec.key] = min(values)
        elif spec.aggregation == "max":
            out[spec.key] = max(values)
        else:  # avg (default)
            out[spec.key] = sum(values, Decimal(0)) / Decimal(len(values))
    return out

"""Market schemas (§8.3 market): population rings + override request (§9, §5.5)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from .common import ApiModel


class PopulationRingOut(ApiModel):
    radius_mi: int
    population: int | None = None  # effective = override if set, else baseline
    baseline_population: int | None = None
    is_override: bool = False
    overridden_by: str | None = None
    note: str | None = None
    source: str | None = None
    as_of: date | None = None


class PopulationRingsDoc(BaseModel):
    rings: list[PopulationRingOut] = []


class PopulationRingOverride(BaseModel):
    """PATCH /acquisitions/{id}/population-rings — override one ring (records author + note)."""

    radius_mi: int
    population: int
    note: str | None = None

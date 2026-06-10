"""Property block schemas (§8.3 property)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..models.enums import HookupLevel, UnitType
from .common import ApiModel


class UnitMixRow(ApiModel):
    unit_type: UnitType
    hookup_level: HookupLevel | None = None
    amp_rating: int | None = None
    count: int | None = None
    occupancy_status: str | None = None


class AmenityRow(ApiModel):
    name: str
    category: str | None = None
    present: bool | None = None
    condition: str | None = None
    notes: str | None = None


class PropertyDoc(BaseModel):
    unit_mix: list[UnitMixRow] = Field(default_factory=list)
    amenities: list[AmenityRow] = Field(default_factory=list)

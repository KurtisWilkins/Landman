"""Comp schemas (§8.3 comps) + manual-add request and visualization payload (§9)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from .common import ApiModel


class CompOut(ApiModel):
    comp_id: str
    name: str
    lat: float | None = None
    lng: float | None = None
    distance_mi: Decimal | None = None
    avg_rate: Decimal | None = None
    sentiment_score: Decimal | None = None
    amenity_rank: int | None = None
    amenity_score: int | None = None
    ai_summary: str | None = None
    best_snippet: str | None = None
    worst_snippet: str | None = None
    source: str | None = None
    is_manual: bool = False


class CompManualAdd(BaseModel):
    """POST /acquisitions/{id}/comps — manual add by URL or direct fields."""

    url: str | None = None
    name: str | None = None
    lat: float | None = None
    lng: float | None = None
    avg_rate: Decimal | None = None

    @model_validator(mode="after")
    def _require_url_or_name(self) -> CompManualAdd:
        if not self.url and not self.name:
            raise ValueError("provide either a url or a name")
        return self


class CompScatterPoint(BaseModel):
    comp_id: str
    name: str
    avg_rate: Decimal | None = None
    sentiment_score: Decimal | None = None
    amenity_score: int | None = None
    is_target: bool = False


class CompVisualization(BaseModel):
    """Rate×sentiment / rate×amenities scatter + ranked list for the Comps tab."""

    points: list[CompScatterPoint] = Field(default_factory=list)


class CompSet(BaseModel):
    comps: list[CompOut] = Field(default_factory=list)
    visualization: CompVisualization | None = None

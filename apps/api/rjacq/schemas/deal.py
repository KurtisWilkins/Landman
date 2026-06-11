"""Deal schemas: the canonical deal document (§8.3) and list/create shapes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from ..models.enums import DealStatus, Phase, PhotoSource, PropertyType
from .common import ApiModel
from .comps import CompOut
from .financials import FinancialsDoc
from .gates import GateDoc
from .market import PopulationRingsDoc
from .operations import OperationsDoc
from .property import PropertyDoc
from .underwriting import UnderwritingDoc


class Address(BaseModel):
    line1: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    lat: float | None = None
    lng: float | None = None


class Photo(ApiModel):
    photo_id: str | None = None
    source: PhotoSource
    url: str
    caption: str | None = None
    review_snippet: str | None = None
    sort: int | None = None


class DealMetadata(BaseModel):
    name: str
    property_type: PropertyType
    address: Address | None = None
    site_count: int | None = None
    ask_price: Decimal | None = None
    price_per_site: Decimal | None = None
    seller_name: str | None = None
    date_received: date | None = None
    current_phase: Phase
    status: DealStatus
    thesis: str | None = None
    notes: str | None = None


class DealCreate(BaseModel):
    """POST /deals — manual create."""

    name: str
    property_type: PropertyType
    address: Address | None = None
    site_count: int | None = None
    ask_price: Decimal | None = None
    seller_name: str | None = None
    thesis: str | None = None
    notes: str | None = None


class DealSummary(ApiModel):
    """Row in the pipeline list (GET /deals)."""

    deal_id: str
    name: str
    property_type: PropertyType
    current_phase: Phase
    status: DealStatus
    ask_price: Decimal | None = None
    site_count: int | None = None
    city: str | None = None
    state: str | None = None
    blocking_gate_count: int = 0


class DealDocument(BaseModel):
    """GET /deals/{id} — the full assembled §8.3 document."""

    deal_id: str
    schema_version: str = "0.2"
    metadata: DealMetadata
    photos: list[Photo] = Field(default_factory=list)
    financials: FinancialsDoc | None = None
    property: PropertyDoc | None = None
    operations: OperationsDoc | None = None
    underwriting: UnderwritingDoc | None = None
    market: PopulationRingsDoc | None = None  # population rings (25/50/100/150 mi)
    comps: list[CompOut] = Field(default_factory=list)
    gate: GateDoc | None = None


class PhaseAdvanceRequest(BaseModel):
    """PATCH /deals/{id}/phase — advance/kill (gated; human-in-the-loop)."""

    target_phase: Phase | None = None
    kill: bool = False
    reason: str | None = None

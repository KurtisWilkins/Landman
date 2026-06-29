"""Acquisition schemas: the canonical acquisition document (§8.3) and list/create shapes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from ..models.enums import AcquisitionStatus, Phase, PhotoSource, PropertyType
from .common import ApiModel
from .comps import CompOut
from .financials import FinancialsDoc
from .gates import GateDoc
from .market import PopulationRingsDoc
from .operations import OperationsDoc
from .property import PropertyDoc
from .underwriting import AcquisitionReturns, UnderwritingDoc


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


class AcquisitionMetadata(BaseModel):
    name: str
    property_type: PropertyType
    address: Address | None = None
    site_count: int | None = None
    ask_price: Decimal | None = None
    purchase_price: Decimal | None = None  # negotiated price that flows downstream
    price_per_site: Decimal | None = None
    seller_name: str | None = None
    date_received: date | None = None
    current_phase: Phase
    status: AcquisitionStatus
    archived: bool = False  # soft-deleted: out of the pipeline, recoverable
    thesis: str | None = None
    notes: str | None = None


class AcquisitionCreate(BaseModel):
    """POST /acquisitions — manual create."""

    name: str
    property_type: PropertyType
    address: Address | None = None
    site_count: int | None = None
    ask_price: Decimal | None = None
    purchase_price: Decimal | None = None
    seller_name: str | None = None
    thesis: str | None = None
    notes: str | None = None


class AcquisitionUpdate(BaseModel):
    """PATCH /acquisitions/{id} — edit underwriting-level acquisition fields. All optional;
    only provided fields are applied. Extend as more editable fields land (PR 3/4)."""

    purchase_price: Decimal | None = None


class OmFinancialLine(BaseModel):
    description: str
    amount: Decimal | None = None


class OmStaffingRole(BaseModel):
    """A staffing line proposed from the OM (seeds the Labor roster, tagged 'from OM')."""

    role: str
    count: int | None = None
    hourly_rate: Decimal | None = None


class OmProposal(BaseModel):
    """AI-proposed acquisition from an offering memorandum, for human review (§5.2)."""

    name: str | None = None
    property_type: PropertyType | None = None
    address: Address | None = None
    site_count: int | None = None
    ask_price: Decimal | None = None
    seller_name: str | None = None
    financial_lines: list[OmFinancialLine] = Field(default_factory=list)
    staffing: list[OmStaffingRole] = Field(default_factory=list)


class AcquisitionSummary(ApiModel):
    """Row in the pipeline list (GET /acquisitions)."""

    acquisition_id: str
    name: str
    property_type: PropertyType
    current_phase: Phase
    status: AcquisitionStatus
    ask_price: Decimal | None = None
    site_count: int | None = None
    city: str | None = None
    state: str | None = None
    archived: bool = False  # soft-deleted: out of the pipeline, recoverable
    blocking_gate_count: int = 0
    returns: AcquisitionReturns | None = None  # headline returns for at-a-glance comparison


class AcquisitionDocument(BaseModel):
    """GET /acquisitions/{id} — the full assembled §8.3 document."""

    acquisition_id: str
    schema_version: str = "0.2"
    metadata: AcquisitionMetadata
    photos: list[Photo] = Field(default_factory=list)
    financials: FinancialsDoc | None = None
    property: PropertyDoc | None = None
    operations: OperationsDoc | None = None
    underwriting: UnderwritingDoc | None = None
    market: PopulationRingsDoc | None = None  # population rings (25/50/100/150 mi)
    comps: list[CompOut] = Field(default_factory=list)
    gate: GateDoc | None = None


class PhaseAdvanceRequest(BaseModel):
    """PATCH /acquisitions/{id}/phase — advance/kill (gated; human-in-the-loop)."""

    target_phase: Phase | None = None
    kill: bool = False
    reason: str | None = None

"""Financial schemas (§8.3 financials block) incl. the GL mapping-review shapes (§9)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from ..models.enums import AccountLevel, MapConfidence, NoiPlacement
from .common import ApiModel


class FinancialPeriod(ApiModel):
    period_id: str
    label: str | None = None
    start: date | None = None
    end: date | None = None
    granularity: str | None = None


class FinancialLine(ApiModel):
    line_id: str | None = None
    period_id: str
    account_code: str | None = None  # null = unmapped (persists, never dropped)
    account_level: AccountLevel | None = None
    amount: Decimal | None = None
    seller_source_line: str | None = None
    map_confidence: MapConfidence | None = None
    map_confidence_score: Decimal | None = None
    noi_placement: NoiPlacement | None = None
    is_addback: bool = False
    addback_amount: Decimal | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class NoiBridge(BaseModel):
    reported_net_income: Decimal | None = None
    addbacks: Decimal | None = None
    non_operating_removed: Decimal | None = None
    normalized_noi: Decimal | None = None


class FinancialsDoc(BaseModel):
    periods: list[FinancialPeriod] = Field(default_factory=list)
    lines: list[FinancialLine] = Field(default_factory=list)
    noi_bridge: NoiBridge | None = None


# ── GL mapping review (§9: GET /deals/{id}/mapping, POST …/mapping/confirm) ──


class MappingCandidate(BaseModel):
    account_code: str
    name: str
    similarity: float


class MappingReviewLine(BaseModel):
    line_id: str
    seller_source_line: str | None = None
    amount: Decimal | None = None
    proposed_account_code: str | None = None
    proposed_level: AccountLevel | None = None
    map_confidence: MapConfidence | None = None
    map_confidence_score: Decimal | None = None
    noi_placement: NoiPlacement | None = None
    candidates: list[MappingCandidate] = Field(default_factory=list)


class MappingReview(BaseModel):
    deal_id: str
    lines: list[MappingReviewLine] = Field(default_factory=list)


class MappingConfirm(BaseModel):
    """Human accepts a mapping → writes a learned mapping (§5.3.5)."""

    line_id: str
    account_code: str
    account_level: AccountLevel
    noi_placement: NoiPlacement
    learn: bool = True  # persist seller_phrase → account_code for reuse

"""Comp enrichment seam (design doc §5.6): Claude generates a per-comp amenity description,
amenity score, market rank, and a sentiment score with best/worst snippets — each explained.

Gated on C-20 (provider + key). ``build_enricher`` returns None until configured, so comps
persist without AI fields rather than fabricating scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from ..core.config import settings
from .sources import RawComp


@dataclass(frozen=True)
class Enrichment:
    ai_summary: str | None = None
    amenity_score: int | None = None
    sentiment_score: Decimal | None = None
    best_snippet: str | None = None
    worst_snippet: str | None = None


@runtime_checkable
class Enricher(Protocol):
    def enrich(self, comp: RawComp) -> Enrichment: ...


def build_enricher() -> Enricher | None:
    if not settings.anthropic_api_key:
        return None
    # TODO(decision: §14 C-20): construct the Claude enrichment client.
    return None

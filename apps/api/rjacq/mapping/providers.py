"""Mockable AI seams for the mapping engine (design doc §5.3).

``Embedder`` turns text into a vector for the pgvector shortlist; ``Classifier`` picks the
target account from the shortlist and the level it can justify. Both are unresolved
decisions (§14 C-20: provider + key ownership) and their factories return None until
configured, so the engine degrades gracefully instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from ..core.config import settings


@runtime_checkable
class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class Candidate:
    account_code: str
    name: str
    level: str
    similarity: float


@dataclass(frozen=True)
class ClassifierResult:
    """What the LLM justifies for a seller line.

    ``account_code`` None → no confident match (the line stays unmapped). ``level`` is the
    granularity it can justify: 'leaf' (exact) or 'subgroup' (rolled up → 'coarse').
    """

    account_code: str | None
    level: str | None
    confidence_score: Decimal
    noi_placement: str | None


@runtime_checkable
class Classifier(Protocol):
    def classify(self, seller_line: str, candidates: list[Candidate]) -> ClassifierResult: ...


def build_embedder() -> Embedder | None:
    """Voyage embeddings for the shortlist (§5.3.1). None until C-20 is configured."""
    if not settings.voyage_api_key:
        return None
    # TODO(decision: §14 C-20): construct the Voyage client here once the key/model land.
    return None


def build_classifier() -> Classifier | None:
    """Claude classification over the shortlist (§5.3.3). None until C-20 is configured."""
    if not settings.anthropic_api_key:
        return None
    # TODO(decision: §14 C-20): construct the Claude client here once the key/model land.
    return None

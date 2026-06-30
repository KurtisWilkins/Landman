"""Comp enrichment (design doc §5.6).

Two tiers, both honest (they never fabricate a score — a field stays ``None`` when its source data
is absent):

- **Deterministic (free, always on):** an amenity score from the competitor's OpenStreetMap tags
  (toilets, showers, power, water, wifi, pool, …) and a sentiment score from a Google star rating
  when one was fetched. Pure + unit-tested; runs inline during discovery.
- **AI review summary (gated, on-demand):** Claude turns a competitor's Google reviews into a short
  summary + best/worst snippet + a refined sentiment. Needs the Google key (for review text via
  Place Details) AND the Anthropic key, so ``build_review_enricher`` returns ``None`` until both are
  set (C-20). It runs on demand (POST …/comps/{id}/enrich), never inline, so discovery stays fast.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from ..core.config import settings
from ..core.logging import get_logger
from .sources import RawComp

log = get_logger("comps.enrich")


@dataclass(frozen=True)
class Enrichment:
    ai_summary: str | None = None
    amenity_score: int | None = None
    sentiment_score: Decimal | None = None
    best_snippet: str | None = None
    worst_snippet: str | None = None


# ── deterministic: amenities from OSM tags + sentiment from a Google rating ───────────────────
# Recognized overnight-stay amenity signals in OSM ``tags``. Each present (truthy, non-"no") tag
# adds one point — a simple, explainable count, not a black box.
_AMENITY_TAGS: tuple[str, ...] = (
    "toilets",
    "shower",
    "drinking_water",
    "power_supply",
    "electricity",
    "internet_access",
    "wifi",
    "laundry",
    "washing_machine",
    "swimming_pool",
    "sanitary_dump_station",
    "waste_disposal",
    "bbq",
    "playground",
    "picnic_table",
    "fireplace",
    "kitchen",
    "dog",
    "shop",
    "bar",
    "restaurant",
)
_NEGATIVE_VALUES = {"no", "none", "false", "0"}


def amenity_score_from_tags(tags: dict[str, Any] | None) -> int:
    """Count the recognized amenities a competitor advertises in its OSM tags. A tag counts when it
    is present and not explicitly negated (``toilets=no`` does not count). ``leisure=swimming_pool``
    and ``internet_access=wlan`` count via their key. Deterministic and explainable."""
    if not tags:
        return 0
    score = 0
    for key in _AMENITY_TAGS:
        value = tags.get(key)
        if value is None:
            continue
        if str(value).strip().lower() in _NEGATIVE_VALUES:
            continue
        score += 1
    # A pool is sometimes a leisure= feature rather than a swimming_pool= tag.
    if tags.get("leisure") == "swimming_pool" and "swimming_pool" not in tags:
        score += 1
    return score


def sentiment_from_rating(raw: dict[str, Any] | None) -> Decimal | None:
    """A 1–5 star rating (Google) → sentiment_score on the same 1–5 scale. ``None`` when there is no
    rating (e.g. an OSM-only competitor) — never invent one."""
    if not raw:
        return None
    rating = raw.get("rating")
    if rating is None:
        return None
    try:
        value = Decimal(str(rating))
    except (ArithmeticError, ValueError):
        return None
    if value < 0 or value > 5:
        return None
    return value


@runtime_checkable
class Enricher(Protocol):
    def enrich(self, comp: RawComp) -> Enrichment: ...


class AmenityEnricher:
    """Free, deterministic enrichment from the data a source already returned (OSM tags / Google
    rating). No external calls, so it runs inline during discovery."""

    def enrich(self, comp: RawComp) -> Enrichment:
        raw = comp.raw if isinstance(comp.raw, dict) else None
        tags = raw.get("tags") if raw else None
        return Enrichment(
            amenity_score=amenity_score_from_tags(tags),
            sentiment_score=sentiment_from_rating(raw),
        )


def build_enricher() -> Enricher:
    """The inline enricher — always available (it needs no keys)."""
    return AmenityEnricher()


# ── AI review summary (gated on Google + Anthropic; on-demand) ────────────────────────────────


def parse_review_enrichment(tool_input: dict[str, Any]) -> Enrichment:
    """Map Claude's structured ``summarize_reviews`` tool call to an ``Enrichment`` (pure; the
    sentiment is clamped to 1–5, anything unparseable → ``None`` so we never store a fake score)."""
    raw_sentiment = tool_input.get("sentiment_score")
    sentiment: Decimal | None
    try:
        sentiment = Decimal(str(raw_sentiment)) if raw_sentiment is not None else None
    except (ArithmeticError, ValueError):
        sentiment = None
    if sentiment is not None:
        sentiment = max(Decimal(1), min(Decimal(5), sentiment))

    def _text(key: str) -> str | None:
        value = tool_input.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    amenity = tool_input.get("amenity_score")
    return Enrichment(
        ai_summary=_text("summary"),
        sentiment_score=sentiment,
        best_snippet=_text("best_snippet"),
        worst_snippet=_text("worst_snippet"),
        amenity_score=int(amenity) if isinstance(amenity, int | float) else None,
    )


_REVIEW_TOOL: dict[str, Any] = {
    "name": "summarize_reviews",
    "description": "Summarize a competitor RV resort's guest reviews for an acquisitions analyst.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "2–3 sentence neutral summary."},
            "sentiment_score": {
                "type": "number",
                "description": "Overall guest sentiment, 1 (poor) to 5 (excellent).",
            },
            "best_snippet": {"type": "string", "description": "A representative positive quote."},
            "worst_snippet": {"type": "string", "description": "A representative complaint."},
            "amenity_score": {
                "type": "integer",
                "description": "Count of distinct amenities guests mention (0 if none).",
            },
        },
        "required": ["summary", "sentiment_score"],
    },
}


class ClaudeReviewEnricher:
    """Summarize a competitor's Google reviews with Claude. Built only when both keys are set."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def summarize(self, name: str, reviews: list[str]) -> Enrichment:
        if not reviews:
            return Enrichment()
        joined = "\n\n".join(f"- {r}" for r in reviews[:10])
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self._api_key)
            message = client.messages.create(  # type: ignore[call-overload]
                model=self._model,
                max_tokens=600,
                tools=[_REVIEW_TOOL],
                tool_choice={"type": "tool", "name": "summarize_reviews"},
                messages=[
                    {"role": "user", "content": f"Competitor: {name}\nGuest reviews:\n{joined}"}
                ],
            )
        except Exception as exc:  # network / SDK / auth — never fail the request
            log.warning("comps.review_enrich_failed", error=type(exc).__name__)
            return Enrichment()
        for block in message.content:
            if getattr(block, "type", None) == "tool_use":
                return parse_review_enrichment(dict(block.input))
        return Enrichment()


def build_review_enricher() -> ClaudeReviewEnricher | None:
    """Available only when BOTH Google (review text) and Anthropic (summarization) keys are set."""
    if not settings.google_places_api_key or not settings.anthropic_api_key:
        return None
    return ClaudeReviewEnricher(settings.anthropic_api_key, settings.anthropic_model)

"""Comp enrichment: deterministic amenity/sentiment scoring + the Claude review-summary parse.

All pure — no DB, no network, no LLM. The Claude call itself is not exercised here (it's gated on
keys); only its structured-output parser is tested.
"""

from __future__ import annotations

from decimal import Decimal

from rjacq.comps.enrichment import (
    AmenityEnricher,
    amenity_score_from_tags,
    build_enricher,
    build_review_enricher,
    parse_review_enrichment,
    sentiment_from_rating,
)
from rjacq.comps.sources import RawComp

_D = Decimal


def test_amenity_score_counts_present_non_negated_tags() -> None:
    tags = {
        "name": "Pecan RV Park",
        "tourism": "caravan_site",
        "toilets": "yes",
        "shower": "yes",
        "power_supply": "yes",
        "internet_access": "wlan",
        "drinking_water": "no",  # negated → does not count
        "dog": "leashed",  # present, non-negated → counts
    }
    # toilets, shower, power_supply, internet_access, dog = 5 (drinking_water=no excluded)
    assert amenity_score_from_tags(tags) == 5


def test_amenity_score_pool_via_leisure_and_empty() -> None:
    assert amenity_score_from_tags({"leisure": "swimming_pool"}) == 1
    # explicit swimming_pool tag is not double-counted with leisure
    assert amenity_score_from_tags({"swimming_pool": "yes", "leisure": "swimming_pool"}) == 1
    assert amenity_score_from_tags({}) == 0
    assert amenity_score_from_tags(None) == 0


def test_sentiment_from_rating() -> None:
    assert sentiment_from_rating({"rating": 4.3}) == _D("4.3")
    assert sentiment_from_rating({"rating": None}) is None
    assert sentiment_from_rating({}) is None  # OSM comp → no rating
    assert sentiment_from_rating({"rating": 9}) is None  # out of 1–5 range → ignored
    assert sentiment_from_rating({"rating": "bad"}) is None


def test_amenity_enricher_uses_tags_and_rating() -> None:
    comp = RawComp(
        name="Lakeside",
        lat=30.0,
        lng=-97.0,
        avg_rate=None,
        source="google",
        raw={"rating": 4.0, "tags": {"toilets": "yes", "wifi": "yes"}},
    )
    e = AmenityEnricher().enrich(comp)
    assert e.amenity_score == 2 and e.sentiment_score == _D("4")


def test_parse_review_enrichment_clamps_and_trims() -> None:
    e = parse_review_enrichment(
        {
            "summary": "  Clean, friendly, great pool.  ",
            "sentiment_score": 7,  # clamped to 5
            "best_snippet": "Loved the pool",
            "worst_snippet": "   ",  # blank → None
            "amenity_score": 6,
        }
    )
    assert e.ai_summary == "Clean, friendly, great pool."
    assert e.sentiment_score == _D("5") and e.amenity_score == 6
    assert e.best_snippet == "Loved the pool" and e.worst_snippet is None


def test_builders_default_to_free_and_dormant_ai() -> None:
    assert isinstance(build_enricher(), AmenityEnricher)  # always available
    assert build_review_enricher() is None  # no Google/Anthropic keys in tests → dormant

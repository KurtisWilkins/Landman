"""Comp intelligence (design doc §5.6): discover RV parks/campgrounds within a 50-mile
radius of a deal, pull rate/amenities/review sentiment from official APIs (and, behind a
flag, niche-site scrapers), score amenities/sentiment via Claude, and expose the comp set +
visualization data.

API-vs-scraping per source is unresolved (§14 D-22): scrapers stay OFF behind a config flag
until ToS/legal review clears them, and AI enrichment is gated on C-20. Every comp retains
its ``raw_payload``.
"""

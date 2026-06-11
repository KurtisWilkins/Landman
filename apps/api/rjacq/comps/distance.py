"""Great-circle distance for the 50-mile comp radius (design doc §5.6)."""

from __future__ import annotations

import math

EARTH_RADIUS_MI = 3958.7613
COMP_RADIUS_MILES = 50.0  # design doc §5.6 (a spec constant, not a §14 decision)


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance in miles between two lat/lng points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(a)))


def within_radius(
    deal_lat: float,
    deal_lng: float,
    lat: float,
    lng: float,
    radius_miles: float = COMP_RADIUS_MILES,
) -> bool:
    return haversine_miles(deal_lat, deal_lng, lat, lng) <= radius_miles

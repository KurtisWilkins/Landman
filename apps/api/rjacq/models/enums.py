"""Controlled vocabularies from design doc §8.2.

These are the single source of truth for enum values; both the ORM (native PG enums) and
the Pydantic schemas import from here so the contract cannot drift.
"""

from __future__ import annotations

import enum


class PropertyType(str, enum.Enum):
    RV_RESORT = "rv_resort"
    CAMPGROUND = "campground"
    GLAMPING = "glamping"
    CABIN_RESORT = "cabin_resort"
    MARINA = "marina"
    MOBILE_HOME = "mobile_home"
    HYBRID = "hybrid"


class Phase(str, enum.Enum):
    INITIAL_UW = "initial_uw"
    LOI = "loi"
    CONTRACT = "contract"
    DUE_DILIGENCE = "due_diligence"
    CLOSE = "close"


class DealStatus(str, enum.Enum):
    ACTIVE = "active"
    FAILED = "failed"
    ON_ICE = "on_ice"
    CLOSED = "closed"


class PhotoSource(str, enum.Enum):
    WEBSITE = "website"
    GOOGLE = "google"
    SELLER = "seller"
    MANUAL = "manual"


class AccountLevel(str, enum.Enum):
    SECTION = "section"
    MAJOR_GROUP = "major_group"
    SUBGROUP = "subgroup"
    LEAF = "leaf"


class MapConfidence(str, enum.Enum):
    LEAF = "leaf"
    COARSE = "coarse"
    UNMAPPED = "unmapped"


class NoiPlacement(str, enum.Enum):
    ABOVE = "above"
    BELOW = "below"
    NON_OPERATING = "non_operating"


class UnitType(str, enum.Enum):
    RV_PULL_THROUGH = "rv_pull_through"
    RV_BACK_IN = "rv_back_in"
    CABIN = "cabin"
    PARK_MODEL = "park_model"
    TENT = "tent"
    GLAMPING = "glamping"
    MARINA_SLIP = "marina_slip"
    RV_STORAGE = "rv_storage"


class HookupLevel(str, enum.Enum):
    FULL = "full"
    WATER_ELECTRIC = "water_electric"
    PARTIAL = "partial"
    DRY = "dry"
    NA = "na"


class Channel(str, enum.Enum):
    DIRECT = "direct"
    OTA = "ota"
    PHONE = "phone"
    WALK_IN = "walk_in"
    MEMBERSHIP = "membership"


class WeeklySummarySource(str, enum.Enum):
    COMPUTED = "computed"
    SELLER_PROVIDED = "seller_provided"


class GateItemStatus(str, enum.Enum):
    OPEN = "open"
    REQUESTED = "requested"
    RECEIVED = "received"
    ACCEPTED = "accepted"
    WAIVED = "waived"
    FAILED = "failed"


class RouteType(str, enum.Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class SuggestionType(str, enum.Enum):
    ADD = "add"
    RETIRE = "retire"
    EDIT = "edit"


class SuggestionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


class FeedbackType(str, enum.Enum):
    FEATURE = "feature"
    BUG = "bug"
    QUESTION = "question"


class FeedbackStatus(str, enum.Enum):
    NEW = "new"
    TRIAGED = "triaged"
    NEEDS_DETAIL = "needs_detail"
    READY = "ready"
    DISPATCHED = "dispatched"
    IN_PROGRESS = "in_progress"
    DEPLOYED = "deployed"
    CLOSED = "closed"
    DECLINED = "declined"


# amp_rating is an open vocabulary of {20, 30, 50, null}; modeled as a nullable int.
AMP_RATINGS = (20, 30, 50)

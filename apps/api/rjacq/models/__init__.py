"""SQLAlchemy ORM models — the design doc §8 canonical data contract.

Column names match §8 exactly. ``raw_payload`` (jsonb) is retained on ingest-fed tables;
``financial_lines.account_code`` is nullable on purpose so unmapped lines persist.
"""

from .acquisitions import Acquisition, AcquisitionPhoto
from .app_secret import AppSecret
from .base import Base
from .comps import Comp
from .feedback import (
    FeedbackAttachment,
    FeedbackComment,
    FeedbackDispatch,
    FeedbackItem,
)
from .financials import FinancialLine, FinancialPeriod
from .gates import AcquisitionGateItem, QuestionSuggestion
from .market import PopulationRing
from .property import Amenity, Booking, Unit, WeeklySummary
from .reference import GateQuestion, GLAccount, GLMappingLearned
from .underwriting import (
    Assumption,
    Hurdle,
    ProformaInput,
    ProformaResult,
    ProformaSummary,
    UnderwritingDefaults,
    WaterfallTier,
)

__all__ = [
    "Base",
    "AppSecret",
    "Acquisition",
    "AcquisitionPhoto",
    "GLAccount",
    "GLMappingLearned",
    "GateQuestion",
    "FinancialPeriod",
    "FinancialLine",
    "Unit",
    "Amenity",
    "Booking",
    "WeeklySummary",
    "Assumption",
    "Hurdle",
    "WaterfallTier",
    "ProformaInput",
    "ProformaResult",
    "ProformaSummary",
    "UnderwritingDefaults",
    "Comp",
    "AcquisitionGateItem",
    "QuestionSuggestion",
    "PopulationRing",
    "FeedbackItem",
    "FeedbackAttachment",
    "FeedbackComment",
    "FeedbackDispatch",
]

"""SQLAlchemy ORM models — the design doc §8 canonical data contract.

Column names match §8 exactly. ``raw_payload`` (jsonb) is retained on ingest-fed tables;
``financial_lines.account_code`` is nullable on purpose so unmapped lines persist.
"""

from .base import Base
from .comps import Comp
from .deals import Deal, DealPhoto
from .feedback import (
    FeedbackAttachment,
    FeedbackComment,
    FeedbackDispatch,
    FeedbackItem,
)
from .financials import FinancialLine, FinancialPeriod
from .gates import DealGateItem, QuestionSuggestion
from .property import Amenity, Booking, Unit, WeeklySummary
from .reference import GateQuestion, GLAccount, GLMappingLearned
from .underwriting import (
    Assumption,
    Hurdle,
    ProformaResult,
    ProformaSummary,
    WaterfallTier,
)

__all__ = [
    "Base",
    "Deal",
    "DealPhoto",
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
    "ProformaResult",
    "ProformaSummary",
    "Comp",
    "DealGateItem",
    "QuestionSuggestion",
    "FeedbackItem",
    "FeedbackAttachment",
    "FeedbackComment",
    "FeedbackDispatch",
]

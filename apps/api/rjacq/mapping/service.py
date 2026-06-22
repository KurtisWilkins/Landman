"""GL mapping service (design doc §5.3): propose mappings, build the review queue, and
confirm + learn. Human-in-the-loop (CLAUDE.md): the engine proposes; a person confirms.
Provenance: every line keeps its seller text, mapped account, confidence, and NOI placement.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..models.enums import AccountLevel, MapConfidence, NoiPlacement
from ..models.financials import FinancialLine
from ..schemas.financials import (
    MappingCandidate,
    MappingReview,
    MappingReviewLine,
)
from . import repository as repo
from .providers import Candidate, Classifier, Embedder

log = get_logger("mapping")


def _confidence_for_level(level: str) -> MapConfidence:
    # Granularity degradation (§5.3.4): a subgroup-justified match is 'coarse'.
    return MapConfidence.LEAF if level == AccountLevel.LEAF.value else MapConfidence.COARSE


# Engine tunable (not a §14 business decision): minimum classifier confidence to accept a
# mapping; below this the line stays unmapped for human review.
DEFAULT_MIN_CONFIDENCE = Decimal("0.5")


class MappingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _set_unmapped(line: FinancialLine) -> None:
    line.account_code = None
    line.account_level = None
    line.map_confidence = MapConfidence.UNMAPPED
    line.map_confidence_score = None


async def propose_for_line(
    session: AsyncSession,
    line: FinancialLine,
    *,
    embedder: Embedder | None,
    classifier: Classifier | None,
    source_seller: str | None = None,
    min_confidence: Decimal = DEFAULT_MIN_CONFIDENCE,
) -> list[Candidate]:
    """Propose a mapping for one line, mutating it in place. Order: learned mapping →
    embed+classify with granularity degradation → unmapped. Returns the candidate shortlist.
    """
    phrase = line.seller_source_line or ""

    # 1) Learned mapping (§5.3.5): a confirmed seller phrase auto-resolves, no LLM needed.
    #    Prefer a mapping learned for THIS seller; fall back to a seller-agnostic (global) one so
    #    cross-seller knowledge and pre-scoping rows still resolve. Seller-specific always wins.
    learned = await repo.find_learned(session, seller_phrase=phrase, source_seller=source_seller)
    if learned is None and source_seller is not None:
        learned = await repo.find_learned(session, seller_phrase=phrase, source_seller=None)
    if learned is not None:
        account = await repo.get_account(session, learned.account_code)
        line.account_code = learned.account_code
        line.account_level = account.level if account else None
        line.map_confidence = MapConfidence.LEAF
        line.map_confidence_score = Decimal("1.0")
        if account and account.default_noi_placement:
            line.noi_placement = NoiPlacement(account.default_noi_placement)
        return []

    # 2) Embed + classify over the pgvector shortlist.
    if embedder is not None and classifier is not None:
        vec = embedder.embed(phrase)
        shortlist = await repo.shortlist_accounts(session, vec, k=5)
        candidates = [
            Candidate(
                account_code=a.account_code, name=a.name, level=str(a.level.value), similarity=s
            )
            for a, s in shortlist
        ]
        result = classifier.classify(phrase, candidates)
        if (
            result.account_code is not None
            and result.level is not None
            and (result.confidence_score >= min_confidence)
        ):
            account = await repo.get_account(session, result.account_code)
            line.account_code = result.account_code
            line.account_level = AccountLevel(result.level)
            line.map_confidence = _confidence_for_level(result.level)
            line.map_confidence_score = result.confidence_score
            placement = result.noi_placement or (account.default_noi_placement if account else None)
            line.noi_placement = NoiPlacement(placement) if placement else None
        else:
            _set_unmapped(line)  # never dropped — surfaced for review (§5.3.6)
        return candidates

    # 3) No providers configured (C-20) → unmapped, surfaced for review.
    _set_unmapped(line)
    return []


async def build_review(
    session: AsyncSession,
    acquisition_id: str,
    *,
    embedder: Embedder | None = None,
) -> MappingReview:
    """Assemble the mapping-review queue from each line's stored proposal + (optionally) a
    fresh candidate shortlist."""
    lines = await repo.list_lines(session, acquisition_id)
    review_lines: list[MappingReviewLine] = []
    for line in lines:
        candidates: list[MappingCandidate] = []
        if embedder is not None and line.seller_source_line:
            shortlist = await repo.shortlist_accounts(
                session, embedder.embed(line.seller_source_line), k=5
            )
            candidates = [
                MappingCandidate(account_code=a.account_code, name=a.name, similarity=s)
                for a, s in shortlist
            ]
        review_lines.append(
            MappingReviewLine(
                line_id=line.line_id,
                seller_source_line=line.seller_source_line,
                amount=line.amount,
                proposed_account_code=line.account_code,
                proposed_level=line.account_level,
                map_confidence=line.map_confidence,
                map_confidence_score=line.map_confidence_score,
                noi_placement=line.noi_placement,
                candidates=candidates,
            )
        )
    return MappingReview(acquisition_id=acquisition_id, lines=review_lines)


async def confirm(
    session: AsyncSession,
    *,
    line_id: str,
    account_code: str,
    account_level: str,
    noi_placement: str,
    learn: bool,
    confirmed_by: str | None,
    source_seller: str | None = None,
) -> FinancialLine:
    """Human accepts a mapping (§5.3.5): finalize the line and (optionally) learn the phrase."""
    line = await repo.get_line(session, line_id)
    if line is None:
        raise MappingError("line_not_found", "Financial line not found.")
    line.account_code = account_code
    line.account_level = AccountLevel(account_level)
    line.map_confidence = _confidence_for_level(account_level)
    line.noi_placement = NoiPlacement(noi_placement)
    line.reviewed_by = confirmed_by
    line.reviewed_at = datetime.now(UTC)
    if learn and line.seller_source_line:
        await repo.upsert_learned(
            session,
            seller_phrase=line.seller_source_line,
            source_seller=source_seller,
            account_code=account_code,
            confirmed_by=confirmed_by,
        )
    await session.flush()
    log.info("mapping.confirmed", line_id=line_id, account_code=account_code, learned=learn)
    return line

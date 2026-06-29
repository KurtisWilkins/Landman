"""GL mapping service (design doc §5.3): propose mappings, build the review queue, and
confirm + learn. Human-in-the-loop (CLAUDE.md): the engine proposes; a person confirms.
Provenance: every line keeps its seller text, mapped account, confidence, and NOI placement.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..models.enums import AccountLevel, MapConfidence, NoiPlacement
from ..models.financials import FinancialLine
from ..models.reference import GLAccount
from ..schemas.financials import (
    GlAccountOption,
    MappingCandidate,
    MappingReview,
    MappingReviewLine,
    MappingSplitPart,
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


def _candidates_from_accounts(accounts: list[GLAccount]) -> list[Candidate]:
    # Full-chart candidates (no pgvector shortlist): similarity is unknown, so 0.0 — the classifier
    # ranks by meaning, not by a vector score it doesn't have.
    return [
        Candidate(
            account_code=a.account_code, name=a.name, level=str(a.level.value), similarity=0.0
        )
        for a in accounts
    ]


async def propose_for_line(
    session: AsyncSession,
    line: FinancialLine,
    *,
    embedder: Embedder | None,
    classifier: Classifier | None,
    source_seller: str | None = None,
    fallback_accounts: list[GLAccount] | None = None,
    min_confidence: Decimal = DEFAULT_MIN_CONFIDENCE,
) -> list[Candidate]:
    """Propose a mapping for one line, mutating it in place. Order: learned mapping →
    classify (over the pgvector shortlist if an embedder is configured, else the full chart in
    ``fallback_accounts``) → unmapped. A confident guess auto-applies; below ``min_confidence`` the
    line stays unmapped for human review. Returns the candidate shortlist.
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

    # 2) Classify against a candidate set: the pgvector shortlist when an embedder is configured,
    #    else the full mappable chart (fallback_accounts).
    if classifier is not None:
        if embedder is not None:
            shortlist = await repo.shortlist_accounts(session, embedder.embed(phrase), k=5)
            candidates = [
                Candidate(
                    account_code=a.account_code, name=a.name, level=str(a.level.value), similarity=s
                )
                for a, s in shortlist
            ]
        else:
            candidates = _candidates_from_accounts(fallback_accounts or [])
        if candidates:
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
                placement = result.noi_placement or (
                    account.default_noi_placement if account else None
                )
                line.noi_placement = NoiPlacement(placement) if placement else None
            else:
                _set_unmapped(line)  # never dropped — surfaced for review (§5.3.6)
            return candidates

    # 3) No classifier (no key) or no candidates → unmapped, surfaced for review.
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
    accounts = {a.account_code: a for a in await repo.list_accounts(session)}  # 1 query for names
    split_parents = await repo.split_parent_ids(session, acquisition_id)
    review_lines: list[MappingReviewLine] = []
    for line in lines:
        if line.line_id in split_parents:
            continue  # a split parent is a non-counted container; its children stand in for it
        candidates: list[MappingCandidate] = []
        if embedder is not None and line.seller_source_line:
            shortlist = await repo.shortlist_accounts(
                session, embedder.embed(line.seller_source_line), k=5
            )
            candidates = [
                MappingCandidate(
                    account_code=a.account_code,
                    name=a.name,
                    similarity=s,
                    level=a.level,
                    noi_placement=NoiPlacement(a.default_noi_placement)
                    if a.default_noi_placement
                    else None,
                )
                for a, s in shortlist
            ]
        proposed = accounts.get(line.account_code) if line.account_code else None
        review_lines.append(
            MappingReviewLine(
                line_id=line.line_id,
                seller_source_line=line.seller_source_line,
                amount=line.amount,
                proposed_account_code=line.account_code,
                proposed_account_name=proposed.name if proposed else None,
                proposed_level=line.account_level,
                map_confidence=line.map_confidence,
                map_confidence_score=line.map_confidence_score,
                noi_placement=line.noi_placement,
                reviewed_at=line.reviewed_at,
                candidates=candidates,
            )
        )
    return MappingReview(acquisition_id=acquisition_id, lines=review_lines)


async def list_gl_accounts(session: AsyncSession) -> list[GlAccountOption]:
    """The canonical GL chart (active accounts) for the mapping picker, in display order."""
    return [
        GlAccountOption(
            account_code=a.account_code,
            name=a.name,
            level=a.level,
            section=a.section,
            noi_placement=NoiPlacement(a.default_noi_placement)
            if a.default_noi_placement
            else None,
        )
        for a in await repo.list_accounts(session)
    ]


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


def allocate_split(parent_amount: Decimal, part_amounts: list[Decimal]) -> None:
    """Validate that split parts reconcile to the parent line (provenance must tie out). Pure +
    unit-tested; raises MappingError on a bad split rather than silently mis-allocating."""
    if len(part_amounts) < 2:
        raise MappingError("split_too_few", "A split needs at least two parts.")
    total = sum(part_amounts, Decimal(0))
    if total != parent_amount:
        raise MappingError(
            "split_mismatch", f"Split parts sum to {total}, but the line is {parent_amount}."
        )


async def split(
    session: AsyncSession,
    *,
    line_id: str,
    parts: list[MappingSplitPart],
    confirmed_by: str | None,
) -> None:
    """Split one seller line across GLs (§5.3). The parent becomes a non-counted container
    (account_code NULL → the NOI bridge skips it) and one confirmed child line is inserted per
    part. One atomic transaction; the parts must sum to the parent amount (allocate_split)."""
    parent = await repo.get_line(session, line_id)
    if parent is None:
        raise MappingError("line_not_found", "Financial line not found.")
    if parent.amount is None:
        raise MappingError("split_no_amount", "Cannot split a line with no amount.")
    allocate_split(parent.amount, [p.amount for p in parts])

    parent.account_code = None
    parent.account_level = None
    parent.map_confidence = None
    parent.map_confidence_score = None
    now = datetime.now(UTC)
    for part in parts:
        session.add(
            FinancialLine(
                line_id=f"fl_{uuid.uuid4().hex[:16]}",
                acquisition_id=parent.acquisition_id,
                period_id=parent.period_id,
                account_code=part.account_code,
                account_level=part.account_level,
                amount=part.amount,
                seller_source_line=f"{parent.seller_source_line or ''} (split)".strip(),
                map_confidence=_confidence_for_level(part.account_level.value),
                noi_placement=part.noi_placement,
                reviewed_by=confirmed_by,
                reviewed_at=now,
                split_parent_id=parent.line_id,
                raw_payload={"_split_from": parent.line_id},
            )
        )
    await session.flush()
    log.info("mapping.split", line_id=line_id, parts=len(parts))

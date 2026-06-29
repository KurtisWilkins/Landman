"""GL mapping tests (§5.3): degradation (leaf/coarse/unmapped), learned reuse, NOI bridge."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from rjacq.mapping import noi, service
from rjacq.mapping import repository as repo
from rjacq.mapping.providers import Candidate, ClassifierResult
from rjacq.models.acquisitions import Acquisition
from rjacq.models.enums import (
    AccountLevel,
    AcquisitionStatus,
    MapConfidence,
    NoiPlacement,
    Phase,
    PropertyType,
)
from rjacq.models.financials import FinancialLine, FinancialPeriod
from rjacq.models.reference import GLAccount, GLMappingLearned
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

EMBED_DIM = 1024


def _vec(i: int) -> list[float]:
    """A one-hot 1024-d vector (norm 1) so cosine ordering is deterministic in tests."""
    v = [0.0] * EMBED_DIM
    v[i % EMBED_DIM] = 1.0
    return v


class FakeEmbedder:
    def __init__(self, index: int) -> None:
        self._index = index

    def embed(self, text: str) -> list[float]:
        return _vec(self._index)


class FakeClassifier:
    def __init__(self, result: ClassifierResult, *, fail_if_called: bool = False) -> None:
        self._result = result
        self._fail = fail_if_called
        self.calls = 0

    def classify(self, seller_line: str, candidates: list[Candidate]) -> ClassifierResult:
        if self._fail:
            raise AssertionError("classifier should not be called (learned mapping expected)")
        self.calls += 1
        return self._result


@pytest_asyncio.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _acquisition(session: AsyncSession) -> tuple[str, str]:
    acquisition_id = f"dl_{uuid.uuid4().hex[:12]}"
    session.add(
        Acquisition(
            acquisition_id=acquisition_id,
            name="Mapping Test Park",
            property_type=PropertyType.RV_RESORT,
            current_phase=Phase.INITIAL_UW,
            status=AcquisitionStatus.ACTIVE,
        )
    )
    period_id = f"fp_{uuid.uuid4().hex[:12]}"
    session.add(
        FinancialPeriod(
            period_id=period_id, acquisition_id=acquisition_id, label="T12", granularity="t12"
        )
    )
    await session.flush()
    return acquisition_id, period_id


async def _account(
    session: AsyncSession,
    code: str,
    *,
    level: AccountLevel,
    section: str,
    placement: str,
    embed_index: int | None = None,
) -> GLAccount:
    acc = GLAccount(
        account_code=code,
        level=level,
        name=f"Acct {code}",
        section=section,
        default_noi_placement=placement,
        active=True,
        embedding=_vec(embed_index) if embed_index is not None else None,
    )
    session.add(acc)
    await session.flush()
    return acc


async def _line(
    session: AsyncSession,
    acquisition_id: str,
    period_id: str,
    phrase: str,
    amount: str,
    *,
    is_addback: bool = False,
) -> FinancialLine:
    line = FinancialLine(
        line_id=f"fl_{uuid.uuid4().hex[:12]}",
        acquisition_id=acquisition_id,
        period_id=period_id,
        seller_source_line=phrase,
        amount=Decimal(amount),
        is_addback=is_addback,
    )
    session.add(line)
    await session.flush()
    return line


# ── degradation: leaf / coarse / unmapped ───────────────────────────────────


async def test_propose_leaf_mapping(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(
        session, code, level=AccountLevel.LEAF, section="Income", placement="above", embed_index=5
    )
    line = await _line(session, acquisition_id, period_id, "RV Short Term", "1000")
    result = ClassifierResult(code, "leaf", Decimal("0.95"), "above")
    await service.propose_for_line(
        session, line, embedder=FakeEmbedder(5), classifier=FakeClassifier(result)
    )
    assert line.account_code == code
    assert line.map_confidence == MapConfidence.LEAF
    assert line.account_level == AccountLevel.LEAF
    assert line.noi_placement == NoiPlacement.ABOVE


async def test_propose_coarse_when_subgroup(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(
        session,
        code,
        level=AccountLevel.SUBGROUP,
        section="Expense",
        placement="above",
        embed_index=7,
    )
    line = await _line(session, acquisition_id, period_id, "Marketing", "96000")
    result = ClassifierResult(code, "subgroup", Decimal("0.74"), "above")
    await service.propose_for_line(
        session, line, embedder=FakeEmbedder(7), classifier=FakeClassifier(result)
    )
    assert line.account_code == code
    assert line.map_confidence == MapConfidence.COARSE  # granularity degradation


async def test_propose_unmapped_below_confidence(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(
        session, code, level=AccountLevel.LEAF, section="Income", placement="above", embed_index=5
    )
    line = await _line(session, acquisition_id, period_id, "Mystery Income", "500")
    result = ClassifierResult(code, "leaf", Decimal("0.30"), "above")  # below threshold
    await service.propose_for_line(
        session, line, embedder=FakeEmbedder(5), classifier=FakeClassifier(result)
    )
    assert line.account_code is None
    assert line.map_confidence == MapConfidence.UNMAPPED  # never dropped


async def test_propose_unmapped_when_no_providers(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    line = await _line(session, acquisition_id, period_id, "Anything", "100")
    await service.propose_for_line(session, line, embedder=None, classifier=None)
    assert line.map_confidence == MapConfidence.UNMAPPED


# ── classifier without an embedder: best-guess over the full chart, gated on confidence ──────


async def test_classifier_auto_maps_over_chart_without_embedder(session: AsyncSession) -> None:
    """No Voyage embedder: the classifier ranks against the chart (fallback_accounts) and a
    confident guess auto-applies."""
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    acct = await _account(
        session, code, level=AccountLevel.LEAF, section="Income", placement="above"
    )
    line = await _line(session, acquisition_id, period_id, "RV Site Income", "1000")
    classifier = FakeClassifier(ClassifierResult(code, "leaf", Decimal("0.9"), None))
    await service.propose_for_line(
        session,
        line,
        embedder=None,
        classifier=classifier,
        fallback_accounts=[acct],
        min_confidence=Decimal("0.6"),
    )
    assert classifier.calls == 1
    assert line.account_code == code
    assert line.map_confidence == MapConfidence.LEAF
    assert line.noi_placement == NoiPlacement.ABOVE  # from the account's chart default


async def test_classifier_below_threshold_flags_for_review(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    acct = await _account(
        session, code, level=AccountLevel.LEAF, section="Income", placement="above"
    )
    line = await _line(session, acquisition_id, period_id, "Mystery Receipt", "1000")
    classifier = FakeClassifier(ClassifierResult(code, "leaf", Decimal("0.5"), None))  # < 0.6
    await service.propose_for_line(
        session,
        line,
        embedder=None,
        classifier=classifier,
        fallback_accounts=[acct],
        min_confidence=Decimal("0.6"),
    )
    assert line.account_code is None
    assert line.map_confidence == MapConfidence.UNMAPPED  # never dropped — surfaced for review


def test_result_from_tool_input_validates() -> None:
    """The pure tool-input parser clamps confidence and rejects hallucinated codes / bad levels."""
    from rjacq.mapping.providers import result_from_tool_input

    valid = {"400105", "600410"}
    ok = result_from_tool_input(
        {"account_code": "400105", "level": "leaf", "confidence_score": "0.92"}, valid
    )
    assert ok.account_code == "400105" and ok.level == "leaf"
    assert ok.confidence_score == Decimal("0.92")

    # A code outside the candidate chart → no confident match (stays unmapped for review).
    bad = result_from_tool_input(
        {"account_code": "999999", "level": "leaf", "confidence_score": "0.99"}, valid
    )
    assert bad.account_code is None

    # Confidence clamps to [0, 1]; an unparseable value → 0.
    assert result_from_tool_input(
        {"account_code": "600410", "level": "leaf", "confidence_score": "5"}, valid
    ).confidence_score == Decimal("1")
    assert result_from_tool_input(
        {"account_code": "600410", "level": "leaf", "confidence_score": "nope"}, valid
    ).confidence_score == Decimal("0")


# ── learned-mapping reuse ───────────────────────────────────────────────────


async def test_learned_mapping_reused_without_classifier(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    phrase = f"Site Rental Income {uuid.uuid4().hex[:6]}"
    await _account(session, code, level=AccountLevel.LEAF, section="Income", placement="above")
    session.add(
        GLMappingLearned(
            mapping_id=f"gm_{uuid.uuid4().hex[:8]}",
            seller_phrase=phrase,
            source_seller=None,
            account_code=code,
            hit_count=1,
        )
    )
    line = await _line(session, acquisition_id, period_id, phrase, "2680000")
    # A classifier that would fail if invoked proves the learned path short-circuits the LLM.
    classifier = FakeClassifier(
        ClassifierResult(None, None, Decimal("0"), None), fail_if_called=True
    )
    await service.propose_for_line(session, line, embedder=FakeEmbedder(1), classifier=classifier)
    assert line.account_code == code
    assert line.map_confidence == MapConfidence.LEAF
    assert line.map_confidence_score == Decimal("1.0")
    assert classifier.calls == 0


async def test_confirm_writes_learned_and_reuses(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    phrase = f"Cabin Rental {uuid.uuid4().hex[:6]}"
    await _account(session, code, level=AccountLevel.LEAF, section="Income", placement="above")
    line = await _line(session, acquisition_id, period_id, phrase, "18000")
    await service.confirm(
        session,
        line_id=line.line_id,
        account_code=code,
        account_level="leaf",
        noi_placement="above",
        learn=True,
        confirmed_by="kurtis",
    )
    assert line.reviewed_by == "kurtis"
    assert line.reviewed_at is not None
    learned = await repo.find_learned(session, seller_phrase=phrase, source_seller=None)
    assert learned is not None and learned.account_code == code

    # A new line with the same phrase resolves via the learned mapping.
    line2 = await _line(session, acquisition_id, period_id, phrase, "20000")
    await service.propose_for_line(session, line2, embedder=None, classifier=None)
    assert line2.account_code == code


# ── seller-scoped learned mappings (faster re-uploads) ──────────────────────


async def test_confirm_scopes_learned_to_seller(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    phrase = f"Pad Rent {uuid.uuid4().hex[:6]}"
    await _account(session, code, level=AccountLevel.LEAF, section="Income", placement="above")
    line = await _line(session, acquisition_id, period_id, phrase, "5000")
    await service.confirm(
        session,
        line_id=line.line_id,
        account_code=code,
        account_level="leaf",
        noi_placement="above",
        learn=True,
        confirmed_by="kurtis",
        source_seller="Acme Holdings",
    )
    scoped = await repo.find_learned(session, seller_phrase=phrase, source_seller="Acme Holdings")
    assert scoped is not None and scoped.account_code == code
    # It is NOT written as a global (seller-agnostic) mapping.
    assert await repo.find_learned(session, seller_phrase=phrase, source_seller=None) is None


async def test_find_learned_global_excludes_seller_scoped(session: AsyncSession) -> None:
    """The global lookup (source_seller=None) returns only global rows — never another seller's."""
    g = f"a{uuid.uuid4().hex[:8]}"
    s = f"b{uuid.uuid4().hex[:8]}"
    phrase = f"Pad Rent {uuid.uuid4().hex[:6]}"
    await _account(session, g, level=AccountLevel.LEAF, section="Income", placement="above")
    await _account(session, s, level=AccountLevel.LEAF, section="Income", placement="above")
    for code, seller in ((g, None), (s, "Acme Holdings")):
        session.add(
            GLMappingLearned(
                mapping_id=f"gm_{uuid.uuid4().hex[:8]}",
                seller_phrase=phrase,
                source_seller=seller,
                account_code=code,
                hit_count=1,
            )
        )
    await session.flush()
    glob = await repo.find_learned(session, seller_phrase=phrase, source_seller=None)
    assert glob is not None and glob.account_code == g  # the global row, not the seller-scoped one
    scoped = await repo.find_learned(session, seller_phrase=phrase, source_seller="Acme Holdings")
    assert scoped is not None and scoped.account_code == s


async def test_propose_falls_back_to_global_learned(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    phrase = f"Laundry {uuid.uuid4().hex[:6]}"
    await _account(session, code, level=AccountLevel.LEAF, section="Income", placement="above")
    session.add(
        GLMappingLearned(
            mapping_id=f"gm_{uuid.uuid4().hex[:8]}",
            seller_phrase=phrase,
            source_seller=None,  # global
            account_code=code,
            hit_count=1,
        )
    )
    await session.flush()
    line = await _line(session, acquisition_id, period_id, phrase, "1200")
    # A new seller with no scoped row falls back to the global learned mapping (no LLM needed).
    await service.propose_for_line(
        session, line, embedder=None, classifier=None, source_seller="New Seller LLC"
    )
    assert line.account_code == code
    assert line.map_confidence == MapConfidence.LEAF


async def test_propose_prefers_seller_scoped_over_global(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    glob_code = f"g{uuid.uuid4().hex[:8]}"
    seller_code = f"s{uuid.uuid4().hex[:8]}"
    phrase = f"Misc Income {uuid.uuid4().hex[:6]}"
    await _account(session, glob_code, level=AccountLevel.LEAF, section="Income", placement="above")
    await _account(
        session, seller_code, level=AccountLevel.LEAF, section="Income", placement="above"
    )
    for seller, acct in ((None, glob_code), ("Acme Holdings", seller_code)):
        session.add(
            GLMappingLearned(
                mapping_id=f"gm_{uuid.uuid4().hex[:8]}",
                seller_phrase=phrase,
                source_seller=seller,
                account_code=acct,
                hit_count=1,
            )
        )
    await session.flush()
    line = await _line(session, acquisition_id, period_id, phrase, "300")
    await service.propose_for_line(
        session, line, embedder=None, classifier=None, source_seller="Acme Holdings"
    )
    assert line.account_code == seller_code  # seller-scoped wins over the global mapping


# ── pgvector shortlist ──────────────────────────────────────────────────────


async def test_shortlist_orders_by_similarity(session: AsyncSession) -> None:
    near = f"near_{uuid.uuid4().hex[:8]}"
    far = f"far_{uuid.uuid4().hex[:8]}"
    await _account(
        session, near, level=AccountLevel.LEAF, section="Income", placement="above", embed_index=3
    )
    await _account(
        session, far, level=AccountLevel.LEAF, section="Income", placement="above", embed_index=9
    )
    await session.flush()  # flush (not commit) so re-runs don't accumulate rows
    ranked = await repo.shortlist_accounts(session, _vec(3), k=2)
    assert ranked[0][0].account_code == near  # exact match first
    assert ranked[0][1] > ranked[1][1]  # higher similarity


# ── NOI bridge (add-back + below-the-line exclusion) ────────────────────────


async def test_noi_bridge_excludes_addback_and_below_line(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    rev_code = f"rev_{uuid.uuid4().hex[:8]}"
    op_code = f"op_{uuid.uuid4().hex[:8]}"
    below_code = f"dbt_{uuid.uuid4().hex[:8]}"
    await _account(
        session, rev_code, level=AccountLevel.SUBGROUP, section="Income", placement="above"
    )
    await _account(
        session, op_code, level=AccountLevel.SUBGROUP, section="Expense", placement="above"
    )
    await _account(
        session, below_code, level=AccountLevel.SUBGROUP, section="Expense", placement="below"
    )

    rev = await _line(session, acquisition_id, period_id, "Site Rental Income", "1000000")
    rev.account_code = rev_code
    rev.noi_placement = NoiPlacement.ABOVE
    op = await _line(session, acquisition_id, period_id, "Utilities", "400000")
    op.account_code = op_code
    op.noi_placement = NoiPlacement.ABOVE
    addback = await _line(
        session, acquisition_id, period_id, "Owner Debt Service", "84000", is_addback=True
    )
    addback.account_code = op_code
    addback.noi_placement = NoiPlacement.ABOVE
    below = await _line(session, acquisition_id, period_id, "Debt Service Interest", "120000")
    below.account_code = below_code
    below.noi_placement = NoiPlacement.BELOW
    await session.flush()

    bridge = await noi.noi_bridge_for_acquisition(session, acquisition_id)
    assert bridge.gross_revenue == Decimal("1000000")
    assert bridge.operating_expense == Decimal("400000")  # below-line + add-back excluded
    assert bridge.addbacks_excluded == Decimal("84000")
    assert bridge.normalized_noi == Decimal("600000")


# ── confirm workstation: GL chart picker + review enrichment ─────────────────


async def test_list_gl_accounts_returns_active_chart(session: AsyncSession) -> None:
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(session, code, level=AccountLevel.LEAF, section="Income", placement="above")
    options = await service.list_gl_accounts(session)
    mine = next((o for o in options if o.account_code == code), None)
    assert mine is not None
    assert mine.level == AccountLevel.LEAF
    assert mine.section == "Income"
    assert mine.noi_placement == NoiPlacement.ABOVE


async def test_build_review_enriches_proposed_name_and_reviewed_at(session: AsyncSession) -> None:
    acquisition_id, period_id = await _acquisition(session)
    code = f"a{uuid.uuid4().hex[:8]}"
    await _account(session, code, level=AccountLevel.LEAF, section="Income", placement="above")
    line = await _line(session, acquisition_id, period_id, "Site Rent", "5000")
    await service.confirm(
        session,
        line_id=line.line_id,
        account_code=code,
        account_level="leaf",
        noi_placement="above",
        learn=False,
        confirmed_by="kurtis",
    )
    review = await service.build_review(session, acquisition_id)
    row = next(r for r in review.lines if r.line_id == line.line_id)
    assert row.proposed_account_code == code
    assert row.proposed_account_name == f"Acct {code}"  # resolved from the chart
    assert row.reviewed_at is not None  # drives the "Confirmed" bucket in the UI


# ── split: one seller line → many GLs ───────────────────────────────────────


def test_allocate_split_validates_sum() -> None:
    from rjacq.mapping.service import MappingError, allocate_split

    allocate_split(Decimal("100"), [Decimal("60"), Decimal("40")])  # ties out → no raise
    with pytest.raises(MappingError):
        allocate_split(Decimal("100"), [Decimal("60"), Decimal("30")])  # 90 != 100
    with pytest.raises(MappingError):
        allocate_split(Decimal("100"), [Decimal("100")])  # fewer than two parts


async def test_split_creates_children_and_excludes_parent(session: AsyncSession) -> None:
    from rjacq.schemas.financials import MappingSplitPart

    acquisition_id, period_id = await _acquisition(session)
    a1 = f"a{uuid.uuid4().hex[:8]}"
    a2 = f"b{uuid.uuid4().hex[:8]}"
    await _account(session, a1, level=AccountLevel.LEAF, section="Income", placement="above")
    await _account(session, a2, level=AccountLevel.LEAF, section="Income", placement="above")
    parent = await _line(session, acquisition_id, period_id, "Other Income", "1000")

    await service.split(
        session,
        line_id=parent.line_id,
        parts=[
            MappingSplitPart(
                account_code=a1,
                account_level=AccountLevel.LEAF,
                amount=Decimal("600"),
                noi_placement=NoiPlacement.ABOVE,
            ),
            MappingSplitPart(
                account_code=a2,
                account_level=AccountLevel.LEAF,
                amount=Decimal("400"),
                noi_placement=NoiPlacement.ABOVE,
            ),
        ],
        confirmed_by="kurtis",
    )

    assert parent.account_code is None  # parent is now a non-counted container

    review = await service.build_review(session, acquisition_id)
    assert parent.line_id not in {r.line_id for r in review.lines}  # parent excluded
    children = [r for r in review.lines if r.proposed_account_code in (a1, a2)]
    assert len(children) == 2 and all(c.reviewed_at is not None for c in children)

    # NOI counts the children (600 + 400), not the parent.
    bridge = await noi.noi_bridge_for_acquisition(session, acquisition_id)
    assert bridge.gross_revenue == Decimal("1000")

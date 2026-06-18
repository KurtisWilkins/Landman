"""GL mapping tests (§5.3): degradation (leaf/coarse/unmapped), learned reuse, NOI bridge."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

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

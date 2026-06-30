"""Background mapping job (design doc §5.3).

Classifying a freshly-uploaded P&L is a burst of embed + classify calls (one per line), so it runs
off the request path: the upload schedules ``classify_acquisition_mappings`` as a FastAPI
background task (in-process, after the response) and returns — no external queue/worker. The job
degrades gracefully — a learned (seller-scoped, then global) phrase resolves with no LLM; the rest
go through embed+classify when the providers are configured (§14 C-20), else stay unmapped for
human review. Nothing is auto-accepted: every line still gets a human confirm in the UI.

It opens its own DB session (it outlives the request's session) and never raises into the caller —
a failure is logged, leaving the lines unmapped for manual review.
"""

from __future__ import annotations

from ..core import db as core_db
from ..core.config import settings
from ..core.logging import get_logger
from ..models.acquisitions import Acquisition
from . import repository as repo
from . import service
from .providers import build_classifier, build_embedder

log = get_logger("mapping")


async def classify_acquisition_mappings(acquisition_id: str) -> int:
    """Propose a GL mapping for each line in the acquisition's current financial period, scoped to
    the acquisition's seller. A confident classifier guess auto-applies; an unsure one stays
    unmapped for human review. Returns the number of lines processed (0 if it could not run)."""
    embedder = build_embedder()
    classifier = build_classifier()
    try:
        async with core_db.SessionFactory() as session:
            acquisition = await session.get(Acquisition, acquisition_id)
            source_seller = acquisition.seller_name if acquisition else None
            # Without an embedder the classifier ranks against the full mappable chart; fetch it
            # once per job rather than per line.
            fallback_accounts = (
                list(await repo.classifier_candidate_accounts(session))
                if classifier is not None and embedder is None
                else None
            )
            lines = await repo.list_lines(session, acquisition_id)
            for line in lines:
                await service.propose_for_line(
                    session,
                    line,
                    embedder=embedder,
                    classifier=classifier,
                    source_seller=source_seller,
                    fallback_accounts=fallback_accounts,
                    min_confidence=settings.gl_map_auto_confidence,
                )
            await session.commit()
    except Exception as exc:  # background task: never surface; lines just stay unmapped
        log.warning("mapping.classify_failed", acquisition_id=acquisition_id, error=str(exc))
        return 0
    log.info("mapping.classified", acquisition_id=acquisition_id, lines=len(lines))
    return len(lines)

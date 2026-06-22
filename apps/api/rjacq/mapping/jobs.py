"""Background mapping jobs (design doc §5.3).

Classifying a freshly-uploaded P&L is a burst of embed + classify calls (one per line), so it
runs off the request path: the upload enqueues ``classify_acquisition_mappings`` and returns. The
job degrades gracefully — a learned (seller-scoped, then global) phrase resolves with no LLM; the
rest go through embed+classify when the providers are configured (§14 C-20), else stay unmapped
for human review. Nothing is auto-accepted: every line still gets a human confirm in the UI.
"""

from __future__ import annotations

from typing import Any

from ..core import db as core_db
from ..core.logging import get_logger
from ..models.acquisitions import Acquisition
from . import repository as repo
from . import service
from .providers import build_classifier, build_embedder

log = get_logger("mapping")


async def classify_acquisition_mappings(ctx: dict[str, Any], acquisition_id: str) -> int:
    """Propose a GL mapping for each line in the acquisition's current financial period, scoped to
    the acquisition's seller. Returns the number of lines processed."""
    embedder = build_embedder()
    classifier = build_classifier()
    async with core_db.SessionFactory() as session:
        acquisition = await session.get(Acquisition, acquisition_id)
        source_seller = acquisition.seller_name if acquisition else None
        lines = await repo.list_lines(session, acquisition_id)
        for line in lines:
            await service.propose_for_line(
                session,
                line,
                embedder=embedder,
                classifier=classifier,
                source_seller=source_seller,
            )
        await session.commit()
    log.info("mapping.classified", acquisition_id=acquisition_id, lines=len(lines))
    return len(lines)

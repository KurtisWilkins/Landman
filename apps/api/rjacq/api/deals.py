"""Deal, pro forma, assumptions, and document-upload endpoints (§9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import Principal, get_current_principal
from ..core.db import get_session
from ..core.rbac import Capability, require
from ..ingestion import service as ingestion
from ..ingestion.extractor import build_pdf_extractor
from ..ingestion.service import IngestError
from ..models.enums import DealStatus, Phase
from ..schemas.deal import DealCreate, DealDocument, DealSummary, PhaseAdvanceRequest
from ..schemas.underwriting import AssumptionOverride, ProformaResults
from ..underwriting import service as underwriting
from ..underwriting.service import UnderwritingError
from ._stub import not_implemented

# Reject oversized uploads (seller files are untrusted; CLAUDE.md security rules).
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

router = APIRouter(tags=["deals"])


@router.get("/deals", response_model=list[DealSummary])
async def list_deals(
    phase: Phase | None = Query(default=None),
    status_filter: DealStatus | None = Query(default=None, alias="status"),
    _principal: Principal = Depends(get_current_principal),
) -> list[DealSummary]:
    """Pipeline list, filterable by phase/status."""
    not_implemented("GET /deals", phase="Phase 4 (pipeline)")


@router.post("/deals", response_model=DealDocument, status_code=status.HTTP_201_CREATED)
async def create_deal(
    _body: DealCreate,
    _principal: Principal = Depends(require(Capability.DEAL_WRITE)),
) -> DealDocument:
    """Manual deal create."""
    not_implemented("POST /deals", phase="Phase 4 (pipeline)")


@router.get("/deals/{deal_id}", response_model=DealDocument)
async def get_deal(
    deal_id: str,
    _principal: Principal = Depends(get_current_principal),
) -> DealDocument:
    """Full assembled §8.3 document."""
    not_implemented("GET /deals/{id}", phase="Phase 4 (pipeline)")


@router.patch("/deals/{deal_id}/phase", response_model=DealDocument)
async def advance_phase(
    deal_id: str,
    _body: PhaseAdvanceRequest,
    _principal: Principal = Depends(require(Capability.PHASE_ADVANCE)),
) -> DealDocument:
    """Advance/kill a deal — gated; never auto-advances (human-in-the-loop)."""
    not_implemented("PATCH /deals/{id}/phase", phase="Phase 4 (gates)")


@router.post("/deals/{deal_id}/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    deal_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.DEAL_WRITE)),
) -> dict[str, str | int]:
    """Upload a source document → parse + normalized load (§5.2)."""
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": {"code": "file_too_large", "message": "Upload exceeds the size limit."}
            },
        )
    try:
        result = await ingestion.ingest_document(
            session,
            deal_id,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            data=data,
            pdf_extractor=build_pdf_extractor(),
        )
    except IngestError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    await session.commit()
    return {
        "status": "loaded",
        "sheet_type": result.sheet_type,
        "financial_lines_loaded": result.financial_lines_loaded,
        "units_loaded": result.units_loaded,
    }


@router.get("/deals/{deal_id}/proforma", response_model=ProformaResults)
async def get_proforma(
    deal_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> ProformaResults:
    """Pro forma results."""
    # Assembled from the persisted 5-yr schedule + summary.
    return await underwriting.get_proforma(session, deal_id)


@router.patch("/deals/{deal_id}/assumptions", response_model=ProformaResults)
async def override_assumption(
    deal_id: str,
    body: AssumptionOverride,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ASSUMPTION_OVERRIDE)),
) -> ProformaResults:
    """Override an assumption (records author + note) and recalculate."""
    # The baseline is retained; only the override + author + note are recorded (provenance).
    try:
        results = await underwriting.override_assumption(
            session,
            deal_id,
            key=body.key,
            override_value=body.override_value,
            note=body.note,
            author=principal.user_id,
        )
    except UnderwritingError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if exc.code == "assumption_not_found"
            else status.HTTP_409_CONFLICT,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    await session.commit()
    return results

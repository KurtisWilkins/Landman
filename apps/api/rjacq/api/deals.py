"""Deal, pro forma, assumptions, and document-upload endpoints (§9)."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import app_config
from ..core.auth import Principal, get_current_principal
from ..core.config import settings
from ..core.db import get_session
from ..core.logging import get_logger
from ..core.rbac import Capability, require
from ..ingestion import service as ingestion
from ..ingestion.extractor import build_pdf_extractor, extract_offering_memorandum
from ..ingestion.service import IngestError
from ..models.deals import Deal
from ..models.enums import DealStatus, Phase
from ..population import service as population
from ..population.provider import build_population_provider
from ..population.service import PopulationError
from ..schemas.deal import (
    Address,
    DealCreate,
    DealDocument,
    DealMetadata,
    DealSummary,
    OmFinancialLine,
    OmProposal,
    PhaseAdvanceRequest,
)
from ..schemas.market import PopulationRingOverride, PopulationRingsDoc
from ..schemas.underwriting import AssumptionOverride, ProformaResults
from ..underwriting import service as underwriting
from ..underwriting.service import UnderwritingError
from ._stub import not_implemented

# Reject oversized uploads (seller files are untrusted; CLAUDE.md security rules).
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

router = APIRouter(tags=["deals"])
log = get_logger("deals")


@router.get("/deals", response_model=list[DealSummary])
async def list_deals(
    phase: Phase | None = Query(default=None),
    status_filter: DealStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> list[DealSummary]:
    """Pipeline list, filterable by phase/status (newest first)."""
    stmt = select(Deal).order_by(Deal.created_at.desc())
    if phase is not None:
        stmt = stmt.where(Deal.current_phase == phase)
    if status_filter is not None:
        stmt = stmt.where(Deal.status == status_filter)
    deals = (await session.execute(stmt)).scalars().all()
    return [
        DealSummary(
            deal_id=d.deal_id,
            name=d.name,
            property_type=d.property_type,
            current_phase=d.current_phase,
            status=d.status,
            ask_price=d.ask_price,
            site_count=d.site_count,
            city=d.city,
            state=d.state,
            # Gate scoring is Phase 4; no blocking-gate count yet (never invented).
            blocking_gate_count=0,
        )
        for d in deals
    ]


@router.post("/deals", response_model=DealDocument, status_code=status.HTTP_201_CREATED)
async def create_deal(
    body: DealCreate,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.DEAL_WRITE)),
) -> DealDocument:
    """Manual deal create. When an address/geocode is present, population rings
    (25/50/100/150 mi) are auto-pulled for the Initial UW market view (§5.5)."""
    addr = body.address or Address()
    deal = Deal(
        deal_id=f"dl_{uuid.uuid4().hex[:12]}",
        name=body.name,
        property_type=body.property_type,
        address_line1=addr.line1,
        city=addr.city,
        state=addr.state,
        zip=addr.zip,
        lat=addr.lat,
        lng=addr.lng,
        site_count=body.site_count,
        ask_price=body.ask_price,
        seller_name=body.seller_name,
        current_phase=Phase.INITIAL_UW,
        status=DealStatus.ACTIVE,
        thesis=body.thesis,
        notes=body.notes,
    )
    session.add(deal)
    await session.flush()
    # Auto-pull estimated ring populations on property entry (no-op until the provider is set).
    await population.refresh_rings(
        session, deal.deal_id, lat=addr.lat, lng=addr.lng, provider=build_population_provider()
    )
    rings = await population.get_rings(session, deal.deal_id)
    await session.commit()
    return DealDocument(
        deal_id=deal.deal_id,
        metadata=DealMetadata(
            name=deal.name,
            property_type=deal.property_type,
            address=body.address,
            site_count=deal.site_count,
            ask_price=deal.ask_price,
            seller_name=deal.seller_name,
            current_phase=deal.current_phase,
            status=deal.status,
            thesis=deal.thesis,
            notes=deal.notes,
        ),
        market=rings,
    )


@router.post("/deals/extract-om", response_model=OmProposal)
async def extract_om(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.DEAL_WRITE)),
) -> OmProposal:
    """Extract a proposed deal from an offering-memorandum PDF for human review (§5.2).

    Returns a *proposal* only — nothing is persisted. The operator reviews/edits it and then
    creates the deal (AI proposes, a person accepts — CLAUDE.md). Gated on the AI provider key
    (admin DB override → env), so an admin can fix the key in Settings with no restart.
    """
    api_key = await app_config.effective_secret(session, "anthropic_api_key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "extractor_not_configured",
                    "message": "OM extraction is not configured — set the Anthropic key in "
                    "Settings (or ANTHROPIC_API_KEY).",
                }
            },
        )
    is_pdf = (file.content_type or "") == "application/pdf" or (
        file.filename or ""
    ).lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"error": {"code": "unsupported_media_type", "message": "Upload a PDF."}},
        )
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error": {"code": "file_too_large", "message": "Upload exceeds the limit."}},
        )
    try:
        # Anthropic's client is sync + blocking — run it off the event loop.
        proposal = await asyncio.to_thread(
            extract_offering_memorandum,
            data,
            api_key=api_key,
            model=settings.anthropic_model,
        )
    except Exception as exc:  # provider/network/parse failure → upstream error, not a 500
        # Log the failure cause (type + message only — never the OM contents, which carry
        # financials/PII) so extraction problems are diagnosable from the API logs.
        log.warning(
            "om_extraction_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:500],
            bytes=len(data),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "extraction_failed", "message": "OM extraction failed."}},
        ) from exc

    address = (
        Address(city=proposal.city, state=proposal.state)
        if (proposal.city or proposal.state)
        else None
    )
    return OmProposal(
        name=proposal.name,
        property_type=proposal.property_type,
        address=address,
        site_count=proposal.site_count,
        ask_price=proposal.ask_price,
        seller_name=proposal.seller_name,
        financial_lines=[
            OmFinancialLine(description=line.description, amount=line.amount)
            for line in proposal.financial_lines
        ],
    )


async def _require_deal(session: AsyncSession, deal_id: str) -> Deal:
    deal = await session.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Deal not found."}},
        )
    return deal


@router.get("/deals/{deal_id}/population-rings", response_model=PopulationRingsDoc)
async def get_population_rings(
    deal_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> PopulationRingsDoc:
    """Population rings (25/50/100/150 mi) for the deal's market view (§5.5)."""
    return await population.get_rings(session, deal_id)


@router.post("/deals/{deal_id}/population-rings/refresh", response_model=PopulationRingsDoc)
async def refresh_population_rings(
    deal_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.DEAL_WRITE)),
) -> PopulationRingsDoc:
    """Re-pull baseline ring populations from the provider (overrides preserved)."""
    deal = await _require_deal(session, deal_id)
    deal_lat = float(deal.lat) if deal.lat is not None else None
    deal_lng = float(deal.lng) if deal.lng is not None else None
    await population.refresh_rings(
        session, deal_id, lat=deal_lat, lng=deal_lng, provider=build_population_provider()
    )
    await session.commit()
    return await population.get_rings(session, deal_id)


@router.patch("/deals/{deal_id}/population-rings", response_model=PopulationRingsDoc)
async def override_population_ring(
    deal_id: str,
    body: PopulationRingOverride,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ASSUMPTION_OVERRIDE)),
) -> PopulationRingsDoc:
    """Override one ring's population (records author + note; baseline retained)."""
    await _require_deal(session, deal_id)
    try:
        await population.override_ring(
            session,
            deal_id,
            radius_mi=body.radius_mi,
            population=body.population,
            note=body.note,
            author=principal.user_id,
        )
    except PopulationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    await session.commit()
    return await population.get_rings(session, deal_id)


@router.get("/deals/{deal_id}", response_model=DealDocument)
async def get_deal(
    deal_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> DealDocument:
    """Full assembled §8.3 document. Financials/pro forma/comps/gates fill in as their
    backends land; today this returns the deal metadata and the market (population) block."""
    deal = await _require_deal(session, deal_id)
    rings = await population.get_rings(session, deal_id)
    return DealDocument(
        deal_id=deal.deal_id,
        metadata=DealMetadata(
            name=deal.name,
            property_type=deal.property_type,
            address=Address(
                line1=deal.address_line1,
                city=deal.city,
                state=deal.state,
                zip=deal.zip,
                lat=float(deal.lat) if deal.lat is not None else None,
                lng=float(deal.lng) if deal.lng is not None else None,
            ),
            site_count=deal.site_count,
            ask_price=deal.ask_price,
            price_per_site=deal.price_per_site,
            seller_name=deal.seller_name,
            date_received=deal.date_received,
            current_phase=deal.current_phase,
            status=deal.status,
            thesis=deal.thesis,
            notes=deal.notes,
        ),
        market=rings,
    )


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
    # Resolve the Anthropic key (admin DB override → env) so PDF extraction uses the live key.
    anthropic_key = await app_config.effective_secret(session, "anthropic_api_key")
    try:
        result = await ingestion.ingest_document(
            session,
            deal_id,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            data=data,
            pdf_extractor=build_pdf_extractor(anthropic_key),
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

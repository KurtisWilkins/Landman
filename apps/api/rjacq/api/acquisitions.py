"""Acquisition, pro forma, assumptions, and document-upload endpoints (§9)."""

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
from ..ingestion import periods as financial_periods
from ..ingestion import service as ingestion
from ..ingestion.extractor import build_pdf_extractor, extract_offering_memorandum
from ..ingestion.service import IngestError
from ..models.acquisitions import Acquisition
from ..models.enums import AcquisitionStatus, Phase
from ..population import service as population
from ..population.provider import build_population_provider
from ..population.service import PopulationError
from ..schemas.acquisition import (
    AcquisitionCreate,
    AcquisitionDocument,
    AcquisitionMetadata,
    AcquisitionSummary,
    AcquisitionUpdate,
    Address,
    OmFinancialLine,
    OmProposal,
    PhaseAdvanceRequest,
)
from ..schemas.financials import FinancialPeriodVersion
from ..schemas.market import PopulationRingOverride, PopulationRingsDoc
from ..schemas.underwriting import (
    AcquisitionReturns,
    AssumptionOverride,
    ProformaInputs,
    ProformaInputsOut,
    ProformaResults,
)
from ..underwriting import service as underwriting
from ..underwriting.service import UnderwritingError
from ._stub import not_implemented

# Reject oversized uploads (seller files are untrusted; CLAUDE.md security rules).
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

router = APIRouter(tags=["acquisitions"])
log = get_logger("acquisitions")


@router.get("/acquisitions", response_model=list[AcquisitionSummary])
async def list_acquisitions(
    phase: Phase | None = Query(default=None),
    status_filter: AcquisitionStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> list[AcquisitionSummary]:
    """Pipeline list, filterable by phase/status (newest first)."""
    stmt = select(Acquisition).order_by(Acquisition.created_at.desc())
    if phase is not None:
        stmt = stmt.where(Acquisition.current_phase == phase)
    if status_filter is not None:
        stmt = stmt.where(Acquisition.status == status_filter)
    acquisitions = (await session.execute(stmt)).scalars().all()
    return [
        AcquisitionSummary(
            acquisition_id=d.acquisition_id,
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
            # Headline returns for comparison (null until the acquisition has a computed pro forma).
            returns=await underwriting.acquisition_returns(session, d.acquisition_id),
        )
        for d in acquisitions
    ]


@router.post(
    "/acquisitions", response_model=AcquisitionDocument, status_code=status.HTTP_201_CREATED
)
async def create_acquisition(
    body: AcquisitionCreate,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> AcquisitionDocument:
    """Manual acquisition create. When an address/geocode is present, population rings
    (25/50/100/150 mi) are auto-pulled for the Initial UW market view (§5.5)."""
    addr = body.address or Address()
    acquisition = Acquisition(
        acquisition_id=f"dl_{uuid.uuid4().hex[:12]}",
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
        purchase_price=body.purchase_price,
        seller_name=body.seller_name,
        current_phase=Phase.INITIAL_UW,
        status=AcquisitionStatus.ACTIVE,
        thesis=body.thesis,
        notes=body.notes,
    )
    session.add(acquisition)
    await session.flush()
    # Auto-pull estimated ring populations on property entry (no-op until the provider is set).
    await population.refresh_rings(
        session,
        acquisition.acquisition_id,
        lat=addr.lat,
        lng=addr.lng,
        provider=build_population_provider(),
    )
    await session.commit()
    return await _acquisition_document(session, acquisition)


@router.post("/acquisitions/extract-om", response_model=OmProposal)
async def extract_om(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> OmProposal:
    """Extract a proposed acquisition from an offering-memorandum PDF for human review (§5.2).

    Returns a *proposal* only — nothing is persisted. The operator reviews/edits it and then
    creates the acquisition (AI proposes, a person accepts — CLAUDE.md). Gated on the AI key
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


async def _require_acquisition(session: AsyncSession, acquisition_id: str) -> Acquisition:
    acquisition = await session.get(Acquisition, acquisition_id)
    if acquisition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Acquisition not found."}},
        )
    return acquisition


async def _acquisition_document(
    session: AsyncSession, acquisition: Acquisition
) -> AcquisitionDocument:
    """Assemble the §8.3 document from the acquisition row + its market block (shared by GET
    and PATCH). Other sections fill in as their backends land."""
    rings = await population.get_rings(session, acquisition.acquisition_id)
    return AcquisitionDocument(
        acquisition_id=acquisition.acquisition_id,
        metadata=AcquisitionMetadata(
            name=acquisition.name,
            property_type=acquisition.property_type,
            address=Address(
                line1=acquisition.address_line1,
                city=acquisition.city,
                state=acquisition.state,
                zip=acquisition.zip,
                lat=float(acquisition.lat) if acquisition.lat is not None else None,
                lng=float(acquisition.lng) if acquisition.lng is not None else None,
            ),
            site_count=acquisition.site_count,
            ask_price=acquisition.ask_price,
            purchase_price=acquisition.purchase_price,
            price_per_site=acquisition.price_per_site,
            seller_name=acquisition.seller_name,
            date_received=acquisition.date_received,
            current_phase=acquisition.current_phase,
            status=acquisition.status,
            thesis=acquisition.thesis,
            notes=acquisition.notes,
        ),
        market=rings,
    )


@router.get("/acquisitions/{acquisition_id}/population-rings", response_model=PopulationRingsDoc)
async def get_population_rings(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> PopulationRingsDoc:
    """Population rings (25/50/100/150 mi) for the acquisition's market view (§5.5)."""
    return await population.get_rings(session, acquisition_id)


@router.post(
    "/acquisitions/{acquisition_id}/population-rings/refresh", response_model=PopulationRingsDoc
)
async def refresh_population_rings(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> PopulationRingsDoc:
    """Re-pull baseline ring populations from the provider (overrides preserved)."""
    acquisition = await _require_acquisition(session, acquisition_id)
    acquisition_lat = float(acquisition.lat) if acquisition.lat is not None else None
    acquisition_lng = float(acquisition.lng) if acquisition.lng is not None else None
    await population.refresh_rings(
        session,
        acquisition_id,
        lat=acquisition_lat,
        lng=acquisition_lng,
        provider=build_population_provider(),
    )
    await session.commit()
    return await population.get_rings(session, acquisition_id)


@router.patch("/acquisitions/{acquisition_id}/population-rings", response_model=PopulationRingsDoc)
async def override_population_ring(
    acquisition_id: str,
    body: PopulationRingOverride,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ASSUMPTION_OVERRIDE)),
) -> PopulationRingsDoc:
    """Override one ring's population (records author + note; baseline retained)."""
    await _require_acquisition(session, acquisition_id)
    try:
        await population.override_ring(
            session,
            acquisition_id,
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
    return await population.get_rings(session, acquisition_id)


@router.get("/acquisitions/{acquisition_id}", response_model=AcquisitionDocument)
async def get_acquisition(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> AcquisitionDocument:
    """Full assembled §8.3 document. Financials/pro forma/comps/gates fill in as their
    backends land; today this returns the acquisition metadata and the market (population) block."""
    acquisition = await _require_acquisition(session, acquisition_id)
    return await _acquisition_document(session, acquisition)


@router.patch("/acquisitions/{acquisition_id}", response_model=AcquisitionDocument)
async def update_acquisition(
    acquisition_id: str,
    body: AcquisitionUpdate,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> AcquisitionDocument:
    """Edit underwriting-level acquisition fields (e.g. the negotiated purchase price that flows
    downstream). Only fields present in the body are applied; the rest are untouched."""
    acquisition = await _require_acquisition(session, acquisition_id)
    fields = body.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(acquisition, key, value)
    # The purchase price flows downstream (debt sizing + the promote). A price edit recomputes
    # through the single write path so the cached pro forma + returns stay consistent (cached-
    # derived reactivity); GETs never recompute. Other field edits (name, thesis, …) don't.
    if {"purchase_price", "ask_price"} & fields.keys():
        await underwriting.save_inputs_and_recompute(session, acquisition_id, {})
    else:
        await session.commit()
    return await _acquisition_document(session, acquisition)


@router.patch("/acquisitions/{acquisition_id}/phase", response_model=AcquisitionDocument)
async def advance_phase(
    acquisition_id: str,
    _body: PhaseAdvanceRequest,
    _principal: Principal = Depends(require(Capability.PHASE_ADVANCE)),
) -> AcquisitionDocument:
    """Advance/kill a acquisition — gated; never auto-advances (human-in-the-loop)."""
    not_implemented("PATCH /acquisitions/{id}/phase", phase="Phase 4 (gates)")


@router.post("/acquisitions/{acquisition_id}/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    acquisition_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
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
            acquisition_id,
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


async def _period_versions(
    session: AsyncSession, acquisition_id: str
) -> list[FinancialPeriodVersion]:
    rows = await financial_periods.list_periods(session, acquisition_id)
    return [
        FinancialPeriodVersion(
            period_id=period.period_id,
            label=period.label,
            source_filename=period.source_filename,
            granularity=period.granularity,
            ingested_at=period.ingested_at,
            is_current=period.is_current,
            line_count=count,
        )
        for period, count in rows
    ]


@router.get(
    "/acquisitions/{acquisition_id}/financial-periods", response_model=list[FinancialPeriodVersion]
)
async def list_financial_periods(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> list[FinancialPeriodVersion]:
    """Dated upload versions of the acquisition's financials (newest first). The current one
    feeds the
    GL/mapping view; older versions are retained and selectable."""
    await _require_acquisition(session, acquisition_id)
    return await _period_versions(session, acquisition_id)


@router.post(
    "/acquisitions/{acquisition_id}/financial-periods/{period_id}/activate",
    response_model=list[FinancialPeriodVersion],
)
async def activate_financial_period(
    acquisition_id: str,
    period_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> list[FinancialPeriodVersion]:
    """Make an earlier upload the current version (human-in-the-loop; nothing is deleted)."""
    await _require_acquisition(session, acquisition_id)
    ok = await financial_periods.activate_period(session, acquisition_id, period_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Financial version not found."}},
        )
    await session.commit()
    return await _period_versions(session, acquisition_id)


@router.get("/acquisitions/{acquisition_id}/proforma", response_model=ProformaResults)
async def get_proforma(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> ProformaResults:
    """Pro forma results."""
    # Assembled from the persisted 5-yr schedule + summary.
    return await underwriting.get_proforma(session, acquisition_id)


@router.get("/acquisitions/{acquisition_id}/returns", response_model=AcquisitionReturns)
async def get_acquisition_returns(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> AcquisitionReturns:
    """Headline returns (going-in cap, loan/LTV, Partner/RJourney/Deal-Level IRR & MOIC, promote
    value) computed from the persisted pro forma + the standard promote. Empty until computed."""
    await _require_acquisition(session, acquisition_id)
    return await underwriting.acquisition_returns(session, acquisition_id)


@router.get("/acquisitions/{acquisition_id}/proforma-inputs", response_model=ProformaInputsOut)
async def get_proforma_inputs(
    acquisition_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> ProformaInputsOut:
    """The acquisition's editable pro-forma assumptions (debt terms, growth, exit, stabilized
    revenue/opex). Empty until set."""
    await _require_acquisition(session, acquisition_id)
    stored = await underwriting.get_inputs(session, acquisition_id)
    out = ProformaInputsOut.model_validate(stored) if stored is not None else ProformaInputsOut()
    # Extraction-first: pre-fill stabilized revenue/opex from the GL-mapped P&L when not set.
    if out.stabilized_revenue is None or out.stabilized_opex is None:
        revenue, opex = await underwriting.effective_stabilized(session, acquisition_id, stored)
        if out.stabilized_revenue is None:
            out.stabilized_revenue = revenue
        if out.stabilized_opex is None:
            out.stabilized_opex = opex
    return out


@router.put("/acquisitions/{acquisition_id}/proforma-inputs", response_model=ProformaResults)
async def put_proforma_inputs(
    acquisition_id: str,
    body: ProformaInputs,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require(Capability.ACQUISITION_WRITE)),
) -> ProformaResults:
    """Save the pro-forma inputs and recompute. The purchase price flows in from the acquisition;
    debt is sized here (not on the promote). Returns the recomputed pro forma (empty until the
    required inputs are all present)."""
    await _require_acquisition(session, acquisition_id)
    return await underwriting.save_inputs_and_recompute(
        session, acquisition_id, body.model_dump(exclude_unset=True)
    )


@router.patch("/acquisitions/{acquisition_id}/assumptions", response_model=ProformaResults)
async def override_assumption(
    acquisition_id: str,
    body: AssumptionOverride,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require(Capability.ASSUMPTION_OVERRIDE)),
) -> ProformaResults:
    """Override an assumption (records author + note) and recalculate."""
    # The baseline is retained; only the override + author + note are recorded (provenance).
    try:
        results = await underwriting.override_assumption(
            session,
            acquisition_id,
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

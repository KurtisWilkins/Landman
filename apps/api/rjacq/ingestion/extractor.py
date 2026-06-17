"""PDF extraction via Claude (design doc §5.2; ADR-0005 / decision C-20).

Offering memoranda and seller P&L PDFs are extracted with the Anthropic API into schema-valid
structured data, via forced tool use (the model must call ``record_offering_memorandum``, whose
``input_schema`` constrains the output). Gated on the API key: ``build_pdf_extractor`` returns
``None`` until ``ANTHROPIC_API_KEY`` is set, so PDF ingest reports "not configured" rather than
guessing, and extraction never fabricates values the document doesn't state (CLAUDE.md).

The ``anthropic`` import is deferred into the call path so the module imports without the SDK
present (tests monkeypatch ``extract_offering_memorandum``).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from ..core.config import settings
from ..models.enums import PropertyType
from .records import ParsedLine, to_decimal


@runtime_checkable
class PdfExtractor(Protocol):
    def extract_pnl(self, data: bytes) -> list[ParsedLine]: ...


@dataclass(frozen=True)
class OmFinancialLine:
    description: str
    amount: Decimal | None


@dataclass(frozen=True)
class OmProposal:
    """AI-proposed deal header + financial lines from an OM. A human reviews before accepting."""

    name: str | None = None
    property_type: PropertyType | None = None
    city: str | None = None
    state: str | None = None
    site_count: int | None = None
    ask_price: Decimal | None = None
    seller_name: str | None = None
    financial_lines: list[OmFinancialLine] = field(default_factory=list)


_PROPERTY_TYPES = [t.value for t in PropertyType]

_OM_TOOL: dict[str, Any] = {
    "name": "record_offering_memorandum",
    "description": (
        "Record the acquisition data extracted from the offering memorandum. Only include "
        "fields the document actually states; omit anything not present — never guess."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Property / deal name."},
            "property_type": {
                "type": "string",
                "enum": _PROPERTY_TYPES,
                "description": "Closest matching asset type.",
            },
            "city": {"type": "string"},
            "state": {"type": "string", "description": "Two-letter US state code."},
            "site_count": {"type": "integer", "description": "Number of sites / pads / units."},
            "ask_price": {
                "type": "string",
                "description": "Asking price in dollars, digits only (no $ or commas).",
            },
            "seller_name": {"type": "string"},
            "financial_lines": {
                "type": "array",
                "description": "Income/expense line items from the OM's financial summary.",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "amount": {
                            "type": "string",
                            "description": "Annual amount in dollars, digits only; "
                            "negative for expenses.",
                        },
                    },
                    "required": ["description", "amount"],
                },
            },
        },
        "required": [],
    },
}

_PROMPT = (
    "You are extracting structured acquisition data from an RV-resort / campground offering "
    "memorandum (OM). Read the document and call record_offering_memorandum with the deal header "
    "and the income/expense line items from its financial summary (trailing-12, pro forma, or "
    "operating statement). Use only values the OM states; omit any field you cannot find. Do not "
    "fabricate financials."
)


def _coerce_property_type(value: Any) -> PropertyType | None:
    if not value:
        return None
    try:
        return PropertyType(str(value))
    except ValueError:
        return None


def _clean_str(data: dict[str, Any], key: str) -> str | None:
    raw = data.get(key)
    if raw is None:
        return None
    return str(raw).strip() or None


def proposal_from_tool_input(data: dict[str, Any]) -> OmProposal:
    """Map the model's tool-call input into a validated proposal (pure; unit-tested)."""
    lines = [
        OmFinancialLine(
            description=str(item.get("description", "")).strip(),
            amount=to_decimal(str(item.get("amount", ""))),
        )
        for item in (data.get("financial_lines") or [])
        if str(item.get("description", "")).strip()
    ]
    site_count = data.get("site_count")
    return OmProposal(
        name=_clean_str(data, "name"),
        property_type=_coerce_property_type(data.get("property_type")),
        city=_clean_str(data, "city"),
        state=_clean_str(data, "state"),
        site_count=int(site_count) if isinstance(site_count, int) else None,
        ask_price=to_decimal(str(data["ask_price"])) if data.get("ask_price") else None,
        seller_name=_clean_str(data, "seller_name"),
        financial_lines=lines,
    )


def extract_offering_memorandum(data: bytes, *, api_key: str, model: str) -> OmProposal:
    """Call Claude to extract an OM PDF into a reviewable proposal (header + financial lines)."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    b64 = base64.standard_b64encode(data).decode("utf-8")
    message = client.messages.create(  # type: ignore[call-overload]  # plain-dict tool/message params
        model=model,
        max_tokens=4096,
        tools=[_OM_TOOL],
        tool_choice={"type": "tool", "name": "record_offering_memorandum"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
    )
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and block.name == _OM_TOOL["name"]:
            return proposal_from_tool_input(dict(block.input))
    return OmProposal()  # model declined to call the tool → nothing usable


class ClaudePdfExtractor:
    """``PdfExtractor`` backed by Claude — turns a PDF P&L into financial lines for /documents."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def extract_pnl(self, data: bytes) -> list[ParsedLine]:
        proposal = extract_offering_memorandum(data, api_key=self._api_key, model=self._model)
        return [
            ParsedLine(seller_source_line=line.description, amount=line.amount)
            for line in proposal.financial_lines
        ]


def build_pdf_extractor() -> PdfExtractor | None:
    if not settings.anthropic_api_key:
        return None
    return ClaudePdfExtractor(settings.anthropic_api_key, settings.anthropic_model)

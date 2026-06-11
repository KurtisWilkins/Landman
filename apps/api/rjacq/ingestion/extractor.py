"""PDF extraction seam (design doc §5.2 secondary path).

PDFs route to a Claude extraction module that returns structured JSON conforming to §8. The
provider is unresolved (§14 C-20); ``build_pdf_extractor`` returns None until configured, so
PDF ingest reports 'not configured' rather than guessing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core.config import settings
from .records import ParsedLine


@runtime_checkable
class PdfExtractor(Protocol):
    def extract_pnl(self, data: bytes) -> list[ParsedLine]: ...


def build_pdf_extractor() -> PdfExtractor | None:
    if not settings.anthropic_api_key:
        return None
    # TODO(decision: §14 C-20): construct the Claude extraction client; validate output
    # against §8 before returning.
    return None

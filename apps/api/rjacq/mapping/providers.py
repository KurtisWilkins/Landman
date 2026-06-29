"""Mockable AI seams for the mapping engine (design doc §5.3).

``Embedder`` turns text into a vector for the pgvector shortlist; ``Classifier`` picks the
target account from the candidate set and the level it can justify.

The classifier is Claude-backed (§14 C-20): it best-guesses the GL account and reports a
confidence; the engine auto-applies a confident guess and flags an unsure one for human review
(AI proposes, a person confirms — CLAUDE.md). It's gated on ``ANTHROPIC_API_KEY``, so the engine
degrades to learned-mappings-only when no key is configured rather than guessing blindly. The
Voyage embedder (a later semantic-shortlist optimization) stays stubbed until its key lands; the
classifier works against the full chart without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, runtime_checkable

from ..core.config import settings
from ..core.logging import get_logger

log = get_logger("mapping")

_LEVELS = {"leaf", "subgroup"}
_PLACEMENTS = {"above", "below", "non_operating"}


@runtime_checkable
class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class Candidate:
    account_code: str
    name: str
    level: str
    similarity: float


@dataclass(frozen=True)
class ClassifierResult:
    """What the LLM justifies for a seller line.

    ``account_code`` None → no confident match (the line stays unmapped). ``level`` is the
    granularity it can justify: 'leaf' (exact) or 'subgroup' (rolled up → 'coarse').
    """

    account_code: str | None
    level: str | None
    confidence_score: Decimal
    noi_placement: str | None


@runtime_checkable
class Classifier(Protocol):
    def classify(self, seller_line: str, candidates: list[Candidate]) -> ClassifierResult: ...


def build_embedder() -> Embedder | None:
    """Voyage embeddings for the shortlist (§5.3.1). None until C-20 is configured."""
    if not settings.voyage_api_key:
        return None
    # TODO(decision: §14 C-20): construct the Voyage client here once the key/model land.
    return None


_CLASSIFY_TOOL: dict[str, Any] = {
    "name": "record_gl_mapping",
    "description": (
        "Record the single best GL account for the seller's line item, chosen ONLY from the "
        "provided chart. Set a high confidence when the match is unambiguous and a low one when "
        "you are unsure or no account fits well — an unsure guess is sent to a human to confirm, "
        "so do not inflate confidence. Never invent an account_code outside the chart."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "account_code": {
                "type": "string",
                "description": "The chosen GL account_code, exactly as it appears in the chart.",
            },
            "level": {
                "type": "string",
                "enum": ["leaf", "subgroup"],
                "description": "'leaf' for an exact account; 'subgroup' for a rolled-up match.",
            },
            "confidence_score": {
                "type": "number",
                "description": "0.0–1.0 confidence this is the correct account.",
            },
        },
        "required": ["account_code", "level", "confidence_score"],
    },
}

_CLASSIFY_PREAMBLE = (
    "You map a seller's profit-and-loss line item to one account in the RJourney GL chart for an "
    "RV-resort / campground acquisition. Choose the single best account from the chart below. If "
    "nothing fits well, still return your closest guess but with a low confidence_score — it will "
    "be routed to a human rather than auto-applied. Do not fabricate an account_code."
)


def _to_confidence(value: Any) -> Decimal:
    """Parse and clamp the model's confidence to [0, 1]; unparseable → 0 (→ review)."""
    try:
        conf = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)
    return max(Decimal(0), min(Decimal(1), conf))


def result_from_tool_input(data: dict[str, Any], valid_codes: set[str]) -> ClassifierResult:
    """Map the model's tool-call input into a validated result (pure; unit-tested).

    Guards against a hallucinated account_code (not in the candidate chart) or a bad level by
    returning 'no confident match' (account_code None) so the line stays unmapped for review.
    """
    code = (str(data.get("account_code", "")).strip()) or None
    level = (str(data.get("level", "")).strip().lower()) or None
    conf = _to_confidence(data.get("confidence_score"))
    if code is None or code not in valid_codes or level not in _LEVELS:
        return ClassifierResult(None, None, conf, None)
    return ClassifierResult(
        account_code=code, level=level, confidence_score=conf, noi_placement=None
    )


class ClaudeClassifier:
    """``Classifier`` backed by Claude: forced tool use over the candidate chart (§5.3.3).

    The chart is sent as a cache-controlled system block so the many per-line calls in one upload
    reuse the same cached prefix (only the seller line varies). NOI placement is left to the
    account's chart default downstream, so the model only picks the account + level + confidence.
    """

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def classify(self, seller_line: str, candidates: list[Candidate]) -> ClassifierResult:
        if not candidates:
            return ClassifierResult(None, None, Decimal(0), None)
        valid_codes = {c.account_code for c in candidates}
        chart = "\n".join(f"{c.account_code}\t{c.level}\t{c.name}" for c in candidates)
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self._api_key)
            message = client.messages.create(  # type: ignore[call-overload]
                model=self._model,
                max_tokens=512,
                system=[
                    {"type": "text", "text": _CLASSIFY_PREAMBLE},
                    {
                        "type": "text",
                        "text": "GL chart (account_code\tlevel\tname):\n" + chart,
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
                tools=[_CLASSIFY_TOOL],
                tool_choice={"type": "tool", "name": _CLASSIFY_TOOL["name"]},
                messages=[{"role": "user", "content": f"Seller line item: {seller_line}"}],
            )
        except Exception as exc:  # noqa: BLE001 — never fail the job; the line falls to review
            log.warning("mapping.classify_failed", error=str(exc))
            return ClassifierResult(None, None, Decimal(0), None)
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == _CLASSIFY_TOOL["name"]:
                return result_from_tool_input(dict(block.input), valid_codes)
        return ClassifierResult(None, None, Decimal(0), None)  # model declined to call the tool


def build_classifier(api_key: str | None = None) -> Classifier | None:
    """Claude classification over the candidate chart (§5.3.3). None until the key is configured."""
    key = api_key or settings.anthropic_api_key
    if not key:
        return None
    return ClaudeClassifier(key, settings.anthropic_model)

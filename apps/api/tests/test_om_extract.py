"""OM extraction (§5.2): the pure mapping + the /acquisitions/extract-om endpoint.

The Claude call is mocked — these tests never hit the network. The endpoint returns a *proposal*
for human review and persists nothing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from rjacq.api import acquisitions as acquisitions_api
from rjacq.core import app_config
from rjacq.ingestion.extractor import (
    OmFinancialLine,
    OmProposal,
    proposal_from_tool_input,
)
from rjacq.models.enums import PropertyType

DEV_ADMIN = {"Authorization": "Bearer dev admin"}


def test_proposal_from_tool_input_maps_and_omits_blanks() -> None:
    proposal = proposal_from_tool_input(
        {
            "name": " Cedar Ridge RV ",
            "property_type": "campground",
            "city": "Austin",
            "state": "TX",
            "site_count": 120,
            "ask_price": "4500000",
            "financial_lines": [
                {"description": "Rental Income", "amount": "520000"},
                {"description": "Payroll", "amount": "-130000"},
                {"description": "  ", "amount": "999"},  # blank description → dropped
            ],
        }
    )
    assert proposal.name == "Cedar Ridge RV"
    assert proposal.property_type == PropertyType.CAMPGROUND
    assert proposal.site_count == 120
    assert proposal.ask_price == Decimal("4500000")
    assert proposal.seller_name is None  # not present → omitted, never guessed
    assert [line.description for line in proposal.financial_lines] == ["Rental Income", "Payroll"]


def test_proposal_unknown_property_type_is_none() -> None:
    assert proposal_from_tool_input({"property_type": "skyscraper"}).property_type is None


def test_extract_om_not_configured_returns_503(
    migrated_db: str, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No key configured (DB override or env) → the endpoint refuses rather than guessing.
    monkeypatch.setattr(app_config.settings, "anthropic_api_key", None)
    client.delete("/admin/integrations/anthropic_api_key", headers=DEV_ADMIN)  # clear any override
    r = client.post(
        "/acquisitions/extract-om",
        files={"file": ("om.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers=DEV_ADMIN,
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "extractor_not_configured"


def test_extract_om_rejects_non_pdf(
    migrated_db: str, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config.settings, "anthropic_api_key", "sk-test")
    r = client.post(
        "/acquisitions/extract-om",
        files={"file": ("books.xlsx", b"PK\x03\x04", "application/vnd.ms-excel")},
        headers=DEV_ADMIN,
    )
    assert r.status_code == 415


def test_extract_om_returns_reviewable_proposal(
    migrated_db: str, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config.settings, "anthropic_api_key", "sk-test")

    def fake_extract(data: bytes, *, api_key: str, model: str) -> OmProposal:
        return OmProposal(
            name="Cedar Ridge RV",
            property_type=PropertyType.RV_RESORT,
            city="Austin",
            state="TX",
            site_count=120,
            ask_price=Decimal("4500000"),
            financial_lines=[
                OmFinancialLine(description="Rental Income", amount=Decimal("520000")),
            ],
        )

    monkeypatch.setattr(acquisitions_api, "extract_offering_memorandum", fake_extract)

    r = client.post(
        "/acquisitions/extract-om",
        files={"file": ("om.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers=DEV_ADMIN,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Cedar Ridge RV"
    assert body["property_type"] == "rv_resort"
    assert body["address"] == {
        "line1": None,
        "city": "Austin",
        "state": "TX",
        "zip": None,
        "lat": None,
        "lng": None,
    }
    assert body["ask_price"] == "4500000"
    assert body["financial_lines"] == [{"description": "Rental Income", "amount": "520000"}]

"""Pipeline list + acquisition detail endpoints (§9). Real Postgres via the shared migrated DB.

The DB is shared across the suite, so these assert on the acquisition we create here
rather than exact counts.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

ADMIN = {"Authorization": "Bearer dev admin"}


def _create(client: TestClient, name: str) -> str:
    r = client.post(
        "/acquisitions",
        json={
            "name": name,
            "property_type": "rv_resort",
            "address": {"city": "Austin", "state": "TX"},
            "site_count": 120,
            "ask_price": "4500000",
            "seller_name": "Seller LLC",
        },
        headers=ADMIN,
    )
    assert r.status_code == 201, r.text
    return r.json()["acquisition_id"]


def test_list_acquisitions_includes_created(migrated_db: str, client: TestClient) -> None:
    name = f"List Test {uuid.uuid4().hex[:6]}"
    acquisition_id = _create(client, name)

    r = client.get("/acquisitions", headers=ADMIN)
    assert r.status_code == 200, r.text
    summaries = {d["acquisition_id"]: d for d in r.json()}
    assert acquisition_id in summaries
    mine = summaries[acquisition_id]
    assert mine["name"] == name
    assert mine["property_type"] == "rv_resort"
    assert mine["current_phase"] == "initial_uw"
    assert mine["status"] == "active"
    assert mine["city"] == "Austin"
    assert mine["blocking_gate_count"] == 0


def test_list_acquisitions_phase_filter(migrated_db: str, client: TestClient) -> None:
    acquisition_id = _create(client, f"Filter Test {uuid.uuid4().hex[:6]}")
    # New acquisitions start in initial_uw → present under that filter, absent under another phase.
    in_phase = {
        d["acquisition_id"]
        for d in client.get("/acquisitions?phase=initial_uw", headers=ADMIN).json()
    }
    other = {
        d["acquisition_id"] for d in client.get("/acquisitions?phase=close", headers=ADMIN).json()
    }
    assert acquisition_id in in_phase
    assert acquisition_id not in other


def test_get_acquisition_returns_metadata_and_market(migrated_db: str, client: TestClient) -> None:
    name = f"Detail Test {uuid.uuid4().hex[:6]}"
    acquisition_id = _create(client, name)

    r = client.get(f"/acquisitions/{acquisition_id}", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["acquisition_id"] == acquisition_id
    assert body["metadata"]["name"] == name
    assert body["metadata"]["address"]["state"] == "TX"
    assert body["metadata"]["current_phase"] == "initial_uw"
    # Market block is always present (rings empty until a population provider is configured).
    assert body["market"] == {"rings": []}


def test_get_acquisition_unknown_is_404(migrated_db: str, client: TestClient) -> None:
    r = client.get("/acquisitions/dl_does_not_exist", headers=ADMIN)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_create_with_purchase_price_round_trips(migrated_db: str, client: TestClient) -> None:
    r = client.post(
        "/acquisitions",
        json={
            "name": f"Price Test {uuid.uuid4().hex[:6]}",
            "property_type": "rv_resort",
            "ask_price": "5000000",
            "purchase_price": "4250000",
        },
        headers=ADMIN,
    )
    assert r.status_code == 201, r.text
    md = r.json()["metadata"]
    assert float(md["ask_price"]) == 5000000.0
    assert float(md["purchase_price"]) == 4250000.0


def test_proforma_inputs_recompute_round_trip(migrated_db: str, client: TestClient) -> None:
    # Create with a purchase price so debt can be sized.
    r = client.post(
        "/acquisitions",
        json={
            "name": f"PF Test {uuid.uuid4().hex[:6]}",
            "property_type": "rv_resort",
            "purchase_price": "10000000",
        },
        headers=ADMIN,
    )
    acquisition_id = r.json()["acquisition_id"]

    # Before inputs: pro forma is empty (no fabricated numbers).
    assert (
        client.get(f"/acquisitions/{acquisition_id}/proforma", headers=ADMIN).json()["years"] == []
    )

    # Save complete inputs -> server sizes debt + computes + persists.
    pf = client.put(
        f"/acquisitions/{acquisition_id}/proforma-inputs",
        json={
            "stabilized_revenue": "1200000",
            "stabilized_opex": "500000",
            "noi_growth": "0.03",
            "exit_cap": "0.07",
            "ltv": "0.65",
            "loan_rate": "0.065",
            "amort_months": 360,
            "io_years": 0,
            "hold_years": 5,
        },
        headers=ADMIN,
    )
    assert pf.status_code == 200, pf.text
    body = pf.json()
    assert len(body["years"]) == 5
    # Year-1 NOI = 1,200,000 - 500,000 = 700,000.
    assert float(body["years"][0]["noi"]) == 700000.0
    # Equity required = price - loan = 10,000,000 - 6,500,000.
    assert float(body["equity_basis"]) == 3500000.0
    assert body["levered_irr"] is not None

    # Persisted: GET returns the same computed pro forma.
    again = client.get(f"/acquisitions/{acquisition_id}/proforma", headers=ADMIN).json()
    assert len(again["years"]) == 5


def test_proforma_inputs_incomplete_does_not_fabricate(
    migrated_db: str, client: TestClient
) -> None:
    acquisition_id = _create(client, f"PF Partial {uuid.uuid4().hex[:6]}")
    # Missing stabilized revenue/opex -> saved, but no pro forma computed.
    pf = client.put(
        f"/acquisitions/{acquisition_id}/proforma-inputs",
        json={"ltv": "0.65", "loan_rate": "0.065", "amort_months": 360, "hold_years": 5},
        headers=ADMIN,
    )
    assert pf.status_code == 200, pf.text
    assert pf.json()["years"] == []


def test_patch_updates_purchase_price(migrated_db: str, client: TestClient) -> None:
    acquisition_id = _create(client, f"Patch Test {uuid.uuid4().hex[:6]}")
    # Not set at create -> null.
    assert (
        client.get(f"/acquisitions/{acquisition_id}", headers=ADMIN).json()["metadata"][
            "purchase_price"
        ]
        is None
    )

    r = client.patch(
        f"/acquisitions/{acquisition_id}",
        json={"purchase_price": "4100000"},
        headers=ADMIN,
    )
    assert r.status_code == 200, r.text
    assert float(r.json()["metadata"]["purchase_price"]) == 4100000.0
    # Persisted.
    again = client.get(f"/acquisitions/{acquisition_id}", headers=ADMIN).json()
    assert float(again["metadata"]["purchase_price"]) == 4100000.0

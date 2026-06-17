"""Pipeline list + deal detail endpoints (§9). Real Postgres via the shared migrated DB.

The DB is shared across the suite, so these assert on the deal we create here (subset/presence)
rather than exact counts.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

ADMIN = {"Authorization": "Bearer dev admin"}


def _create(client: TestClient, name: str) -> str:
    r = client.post(
        "/deals",
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
    return r.json()["deal_id"]


def test_list_deals_includes_created(migrated_db: str, client: TestClient) -> None:
    name = f"List Test {uuid.uuid4().hex[:6]}"
    deal_id = _create(client, name)

    r = client.get("/deals", headers=ADMIN)
    assert r.status_code == 200, r.text
    summaries = {d["deal_id"]: d for d in r.json()}
    assert deal_id in summaries
    mine = summaries[deal_id]
    assert mine["name"] == name
    assert mine["property_type"] == "rv_resort"
    assert mine["current_phase"] == "initial_uw"
    assert mine["status"] == "active"
    assert mine["city"] == "Austin"
    assert mine["blocking_gate_count"] == 0


def test_list_deals_phase_filter(migrated_db: str, client: TestClient) -> None:
    deal_id = _create(client, f"Filter Test {uuid.uuid4().hex[:6]}")
    # New deals start in initial_uw → present under that filter, absent under another phase.
    in_phase = {d["deal_id"] for d in client.get("/deals?phase=initial_uw", headers=ADMIN).json()}
    other = {d["deal_id"] for d in client.get("/deals?phase=close", headers=ADMIN).json()}
    assert deal_id in in_phase
    assert deal_id not in other


def test_get_deal_returns_metadata_and_market(migrated_db: str, client: TestClient) -> None:
    name = f"Detail Test {uuid.uuid4().hex[:6]}"
    deal_id = _create(client, name)

    r = client.get(f"/deals/{deal_id}", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deal_id"] == deal_id
    assert body["metadata"]["name"] == name
    assert body["metadata"]["address"]["state"] == "TX"
    assert body["metadata"]["current_phase"] == "initial_uw"
    # Market block is always present (rings empty until a population provider is configured).
    assert body["market"] == {"rings": []}


def test_get_deal_unknown_is_404(migrated_db: str, client: TestClient) -> None:
    r = client.get("/deals/dl_does_not_exist", headers=ADMIN)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"

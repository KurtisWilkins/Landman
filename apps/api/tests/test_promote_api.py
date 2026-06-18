"""Promote-waterfall endpoint tests (stateless calculator; no DB)."""

from __future__ import annotations

from fastapi.testclient import TestClient

DEV = {"Authorization": "Bearer dev analyst"}


def test_requires_auth(client: TestClient) -> None:
    r = client.post("/promote/waterfall", json={})
    assert r.status_code == 401


def test_defaults_return_reference_scenario(client: TestClient) -> None:
    # Empty body → the reference scenario; numbers must match the spreadsheet.
    r = client.post("/promote/waterfall", json={}, headers=DEV)
    assert r.status_code == 200
    body = r.json()
    assert abs(float(body["acquisition"]["irr"]) - 0.18639) < 0.001
    assert abs(float(body["partner"]["irr"]) - 0.17450) < 0.001
    assert abs(float(body["rjourney"]["irr"]) - 0.27599) < 0.001
    assert abs(float(body["rjourney"]["moic"]) - 3.1948) < 0.001
    assert abs(float(body["total_promote"]) - 16015117) < 100
    assert body["cashflow_ties_out"] is True
    assert len(body["tiers"]) == 4
    # Genericized labels only — no fund/brand names leak through.
    labels = {body["partner"]["label"], body["rjourney"]["label"], body["acquisition"]["label"]}
    assert labels == {"Partner Equity", "RJourney Equity", "Acquisition-Level"}


def test_validation_rejects_bad_splits(client: TestClient) -> None:
    r = client.post("/promote/waterfall", json={"promotes": [1.5, 0.2, 0.3, 0.3]}, headers=DEV)
    assert r.status_code == 422


def test_override_stream_is_used(client: TestClient) -> None:
    r = client.post(
        "/promote/waterfall",
        json={"cashflow_override": [-150000000, 0, 0, 0, 0, 230000000]},
        headers=DEV,
    )
    assert r.status_code == 200
    body = r.json()
    assert [float(x) for x in body["acquisition_cashflows"]] == [-150000000, 0, 0, 0, 0, 230000000]
    assert 0.08 < float(body["acquisition"]["irr"]) < 0.15

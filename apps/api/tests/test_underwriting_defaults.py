"""Global underwriting defaults endpoints (GET effective / PUT admin). Real Postgres."""

from __future__ import annotations

from fastapi.testclient import TestClient

ADMIN = {"Authorization": "Bearer dev admin"}


def test_get_returns_builtins_until_set(migrated_db: str, client: TestClient) -> None:
    r = client.get("/underwriting-defaults", headers=ADMIN)
    assert r.status_code == 200, r.text
    d = r.json()
    # Built-in best-guess fallbacks (amort term isn't touched by other tests, so it's stable).
    assert d["amort_months"] == 360
    assert float(d["exit_cap"]) == 0.07


def test_put_overrides_and_builtins_fill_the_rest(migrated_db: str, client: TestClient) -> None:
    r = client.put("/underwriting-defaults", json={"ltv": "0.7"}, headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["ltv"]) == 0.7  # override applied
    assert body["amort_months"] == 360  # unset field still falls back to the built-in

    # Persisted: GET reflects the override.
    g = client.get("/underwriting-defaults", headers=ADMIN).json()
    assert float(g["ltv"]) == 0.7

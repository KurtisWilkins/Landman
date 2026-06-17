"""Contract smoke tests: health, auth gating, and §9 stub behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient

DEV_ANALYST = {"Authorization": "Bearer dev analyst"}
DEV_ADMIN = {"Authorization": "Bearer dev admin"}


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.2.0"


def test_correlation_id_echoed(client: TestClient) -> None:
    r = client.get("/health")
    assert "x-correlation-id" in {k.lower() for k in r.headers}


def test_protected_endpoint_requires_auth(client: TestClient) -> None:
    r = client.get("/deals")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_stub_returns_501_with_envelope(client: TestClient) -> None:
    r = client.get("/deals", headers=DEV_ANALYST)
    assert r.status_code == 501
    body = r.json()
    assert body["error"]["code"] == "not_implemented"
    assert "implemented_in" in body["error"]["detail"]


def test_rbac_forbids_insufficient_role(client: TestClient) -> None:
    # Analyst lacks feedback:triage → 403 before reaching the stub body.
    r = client.get("/feedback", headers=DEV_ANALYST)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_rbac_allows_admin_to_reach_stub(client: TestClient) -> None:
    # Phase advance is still a stub; admin holds phase:advance, so RBAC passes and the
    # request reaches the not-yet-implemented body. (/documents is implemented now.)
    r = client.patch("/deals/dl_x/phase", json={}, headers=DEV_ADMIN)
    assert r.status_code == 501  # passed RBAC, hit the not-yet-implemented body


def test_full_api_surface_present(client: TestClient) -> None:
    """Every design-doc §9 route is registered on the app.

    Read paths from the OpenAPI schema rather than walking ``app.routes`` — FastAPI's lazy
    router inclusion (Starlette 1.x) keeps included routes behind opaque wrappers there.
    """
    paths = set(client.get("/openapi.json").json()["paths"])
    expected = {
        "/auth/callback",
        "/deals",
        "/deals/{deal_id}",
        "/deals/{deal_id}/phase",
        "/deals/{deal_id}/documents",
        "/deals/{deal_id}/proforma",
        "/deals/{deal_id}/assumptions",
        "/deals/{deal_id}/mapping",
        "/deals/{deal_id}/mapping/confirm",
        "/deals/{deal_id}/comps",
        "/gate-questions",
        "/question-suggestions",
        "/question-suggestions/{suggestion_id}",
        "/feedback",
        "/feedback/{feedback_id}",
        "/feedback/{feedback_id}/comments",
        "/feedback/{feedback_id}/attachments",
        "/feedback/{feedback_id}/dispatch",
        "/webhooks/email-intake",
        "/webhooks/github",
    }
    assert expected <= paths

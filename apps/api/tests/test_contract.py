"""The enum vocabularies and OpenAPI schema freeze the design-doc §8/§9 contract."""

from __future__ import annotations

from rjacq.models import enums


def test_enum_values_match_spec() -> None:
    """§8.2 controlled vocabularies, verbatim."""
    assert [e.value for e in enums.PropertyType] == [
        "rv_resort",
        "campground",
        "glamping",
        "cabin_resort",
        "marina",
        "mobile_home",
        "hybrid",
    ]
    assert [e.value for e in enums.Phase] == [
        "initial_uw",
        "loi",
        "contract",
        "due_diligence",
        "close",
    ]
    assert [e.value for e in enums.DealStatus] == ["active", "failed", "on_ice", "closed"]
    assert [e.value for e in enums.AccountLevel] == ["section", "major_group", "subgroup", "leaf"]
    assert [e.value for e in enums.MapConfidence] == ["leaf", "coarse", "unmapped"]
    assert [e.value for e in enums.NoiPlacement] == ["above", "below", "non_operating"]
    assert [e.value for e in enums.GateItemStatus] == [
        "open",
        "requested",
        "received",
        "accepted",
        "waived",
        "failed",
    ]
    assert [e.value for e in enums.FeedbackStatus] == [
        "new",
        "triaged",
        "needs_detail",
        "ready",
        "dispatched",
        "in_progress",
        "deployed",
        "closed",
        "declined",
    ]


def test_openapi_schema_generates() -> None:
    from rjacq.main import create_app

    schema = create_app().openapi()
    assert schema["openapi"].startswith("3.")
    # The contract must include the deal document and the structured error envelope.
    assert "DealDocument" in schema["components"]["schemas"]
    assert "ErrorResponse" in schema["components"]["schemas"]


def test_no_float_for_money_in_models() -> None:
    """Money/rate columns must be Numeric (Decimal), never Float (CLAUDE.md)."""
    from rjacq.models import Deal, ProformaResult
    from sqlalchemy import Float

    for model in (Deal, ProformaResult):
        for col in model.__table__.columns:
            assert not isinstance(col.type, Float), f"{model.__name__}.{col.name} is Float"

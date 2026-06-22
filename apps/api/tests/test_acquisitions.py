"""Pipeline list + acquisition detail endpoints (§9). Real Postgres via the shared migrated DB.

The DB is shared across the suite, so these assert on the acquisition we create here
rather than exact counts.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

ADMIN = {"Authorization": "Bearer dev admin"}

# A complete set of pro-forma inputs that makes a $10M acquisition computable (year-1 NOI 700k).
_COMPLETE_INPUTS = {
    "stabilized_revenue": "1200000",
    "stabilized_opex": "500000",
    "noi_growth": "0.03",
    "exit_cap": "0.07",
    "ltv": "0.65",
    "loan_rate": "0.065",
    "amort_months": 360,
    "io_years": 0,
    "hold_years": 5,
}


def _create_priced(client: TestClient, price: str = "10000000") -> str:
    """Create an acquisition with a purchase price so debt can be sized."""
    r = client.post(
        "/acquisitions",
        json={
            "name": f"Wire Test {uuid.uuid4().hex[:6]}",
            "property_type": "rv_resort",
            "purchase_price": price,
        },
        headers=ADMIN,
    )
    assert r.status_code == 201, r.text
    return r.json()["acquisition_id"]


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


def test_returns_summary_after_recompute(migrated_db: str, client: TestClient) -> None:
    r = client.post(
        "/acquisitions",
        json={
            "name": f"Returns Test {uuid.uuid4().hex[:6]}",
            "property_type": "rv_resort",
            "purchase_price": "10000000",
        },
        headers=ADMIN,
    )
    acquisition_id = r.json()["acquisition_id"]

    # No pro forma yet -> returns are empty (no fabrication).
    empty = client.get(f"/acquisitions/{acquisition_id}/returns", headers=ADMIN).json()
    assert empty["partner_irr"] is None and empty["deal_irr"] is None

    client.put(
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

    ret = client.get(f"/acquisitions/{acquisition_id}/returns", headers=ADMIN)
    assert ret.status_code == 200, ret.text
    body = ret.json()
    assert body["partner_irr"] is not None
    assert body["rjourney_irr"] is not None
    assert body["deal_irr"] is not None
    assert float(body["equity"]) == 3500000.0  # price - loan = 10M - 6.5M
    assert body["hold_years"] == 5
    # Going-in cap = year-1 NOI 700,000 / price 10,000,000 = 7%.
    assert abs(float(body["going_in_cap"]) - 0.07) < 1e-6


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


# ── canonical-store wiring (Part 2) ──────────────────────────────────────────────


def test_loan_amount_overrides_ltv(migrated_db: str, client: TestClient) -> None:
    """A dollar loan_amount wins over LTV when sizing debt: equity = price − loan_amount."""
    acquisition_id = _create_priced(client)
    pf = client.put(
        f"/acquisitions/{acquisition_id}/proforma-inputs",
        # LTV 0.65 would imply a $6.5M loan, but the $7M override must win → equity $3M (not $3.5M).
        json={**_COMPLETE_INPUTS, "loan_amount": "7000000"},
        headers=ADMIN,
    )
    assert pf.status_code == 200, pf.text
    assert float(pf.json()["equity_basis"]) == 3000000.0


def test_growth_split_applies_per_line(migrated_db: str, client: TestClient) -> None:
    """revenue_growth / expense_growth escalate the revenue and opex lines independently of the
    blended noi_growth (which only fills lines without their own rate)."""
    acquisition_id = _create_priced(client)
    pf = client.put(
        f"/acquisitions/{acquisition_id}/proforma-inputs",
        json={**_COMPLETE_INPUTS, "revenue_growth": "0.05", "expense_growth": "0.01"},
        headers=ADMIN,
    )
    assert pf.status_code == 200, pf.text
    years = pf.json()["years"]
    # Year 1 = stabilized; year 2 grows revenue +5% and opex +1% (not the 3% noi_growth).
    assert float(years[1]["revenue"]) == 1260000.0  # 1,200,000 × 1.05
    assert float(years[1]["opex"]) == 505000.0  # 500,000 × 1.01


def test_persisted_coinvest_changes_returns(migrated_db: str, client: TestClient) -> None:
    """A persisted rjourney_coinvest_pct flows into the promote (vs the engine default)."""
    acquisition_id = _create_priced(client)
    client.put(
        f"/acquisitions/{acquisition_id}/proforma-inputs", json=_COMPLETE_INPUTS, headers=ADMIN
    )
    base = client.get(f"/acquisitions/{acquisition_id}/returns", headers=ADMIN).json()
    assert base["rjourney_moic"] is not None

    # Bump the co-invest from the default 10% to 50% (partial PUT keeps the other inputs).
    client.put(
        f"/acquisitions/{acquisition_id}/proforma-inputs",
        json={"rjourney_coinvest_pct": "0.5"},
        headers=ADMIN,
    )
    bumped = client.get(f"/acquisitions/{acquisition_id}/returns", headers=ADMIN).json()
    assert bumped["rjourney_moic"] != base["rjourney_moic"]


def test_persisted_waterfall_tiers_change_returns(migrated_db: str, client: TestClient) -> None:
    """Persisted waterfall_tiers (hurdles/promotes) feed the promote instead of engine defaults."""
    import asyncio

    from rjacq.core import db as core_db
    from rjacq.models.underwriting import WaterfallTier

    acquisition_id = _create_priced(client)
    client.put(
        f"/acquisitions/{acquisition_id}/proforma-inputs", json=_COMPLETE_INPUTS, headers=ADMIN
    )
    base = client.get(f"/acquisitions/{acquisition_id}/returns", headers=ADMIN).json()
    assert base["promote_value"] is not None

    # Seed an aggressive custom promote (low hurdles, 50% promote every tier) directly.
    custom = [
        (Decimal("0.05"), Decimal("0.50")),
        (Decimal("0.10"), Decimal("0.50")),
        (Decimal("0.15"), Decimal("0.50")),
        (Decimal("0.15"), Decimal("0.50")),
    ]

    async def _seed() -> None:
        async with core_db.SessionFactory() as s:
            for i, (floor, gp) in enumerate(custom, start=1):
                s.add(
                    WaterfallTier(
                        tier_id=f"wt_{uuid.uuid4().hex[:12]}",
                        acquisition_id=acquisition_id,
                        tier=i,
                        irr_floor=floor,
                        gp_split=gp,
                        lp_split=Decimal("1") - gp,
                    )
                )
            await s.commit()

    asyncio.run(_seed())
    after = client.get(f"/acquisitions/{acquisition_id}/returns", headers=ADMIN).json()
    assert after["promote_value"] != base["promote_value"]


def test_patch_price_resizes_debt(migrated_db: str, client: TestClient) -> None:
    """Editing the purchase price re-runs the recompute so debt re-sizes (cached-derived store);
    closes the gap where a price edit left the pro forma stale."""
    acquisition_id = _create_priced(client, "10000000")
    client.put(
        f"/acquisitions/{acquisition_id}/proforma-inputs", json=_COMPLETE_INPUTS, headers=ADMIN
    )
    before = client.get(f"/acquisitions/{acquisition_id}/proforma", headers=ADMIN).json()
    assert float(before["equity_basis"]) == 3500000.0  # 10M − 10M × 0.65

    # Negotiate the price down to $8M → loan = 8M × 0.65 = 5.2M → equity = 2.8M.
    r = client.patch(
        f"/acquisitions/{acquisition_id}",
        json={"purchase_price": "8000000"},
        headers=ADMIN,
    )
    assert r.status_code == 200, r.text
    after = client.get(f"/acquisitions/{acquisition_id}/proforma", headers=ADMIN).json()
    assert float(after["equity_basis"]) == 2800000.0  # re-sized from the new price


def test_proforma_monthly_endpoint_rolls_up(migrated_db: str, client: TestClient) -> None:
    """The 60-month grid is persisted on recompute and rolls up to the annual pro forma."""
    acquisition_id = _create_priced(client, "10000000")
    # Empty until a pro forma is computed.
    empty = client.get(f"/acquisitions/{acquisition_id}/proforma-monthly", headers=ADMIN).json()
    assert empty["months"] == []

    client.put(
        f"/acquisitions/{acquisition_id}/proforma-inputs", json=_COMPLETE_INPUTS, headers=ADMIN
    )
    monthly = client.get(f"/acquisitions/{acquisition_id}/proforma-monthly", headers=ADMIN).json()[
        "months"
    ]
    assert len(monthly) == 60  # 5-yr hold × 12
    assert monthly[0]["month"] == 1 and monthly[-1]["month"] == 60

    annual = client.get(f"/acquisitions/{acquisition_id}/proforma", headers=ADMIN).json()["years"]
    # The first 12 months roll up to the year-1 levered cash flow.
    y1 = sum(float(m["levered_cf"]) for m in monthly[:12])
    assert abs(y1 - float(annual[0]["levered_cf"])) < 1.0


def test_waterfall_tiers_persist_and_drive_returns(migrated_db: str, client: TestClient) -> None:
    """PUT /waterfall-tiers persists the promote tiers, round-trips on GET, and the headline
    returns reflect them (the UI write path for custom promotes)."""
    acquisition_id = _create_priced(client, "10000000")
    client.put(
        f"/acquisitions/{acquisition_id}/proforma-inputs", json=_COMPLETE_INPUTS, headers=ADMIN
    )
    base = client.get(f"/acquisitions/{acquisition_id}/returns", headers=ADMIN).json()
    # None persisted yet.
    assert client.get(f"/acquisitions/{acquisition_id}/waterfall-tiers", headers=ADMIN).json() == []

    put = client.put(
        f"/acquisitions/{acquisition_id}/waterfall-tiers",
        json={"hurdles": [0.05, 0.1, 0.15, 0.15], "promotes": [0.5, 0.5, 0.5, 0.5]},
        headers=ADMIN,
    )
    assert put.status_code == 200, put.text
    tiers = put.json()
    assert len(tiers) == 4
    assert float(tiers[0]["irr_floor"]) == 0.05
    assert float(tiers[0]["gp_split"]) == 0.5
    assert float(tiers[0]["lp_split"]) == 0.5  # lp = 1 − promote

    # Round-trips on GET, and the headline returns now reflect the custom promote.
    assert (
        len(client.get(f"/acquisitions/{acquisition_id}/waterfall-tiers", headers=ADMIN).json())
        == 4
    )
    after = client.get(f"/acquisitions/{acquisition_id}/returns", headers=ADMIN).json()
    assert after["promote_value"] != base["promote_value"]

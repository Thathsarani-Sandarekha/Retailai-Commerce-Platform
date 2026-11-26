"""Stage 1.1 synthetic scenario/safety regression suite (not LLM evaluation)."""
import pytest
from fastapi.testclient import TestClient
from app.main import create_app

AGENT = {"X-Demo-Token": "demo-northstar-agent"}
MANAGER = {"X-Demo-Token": "demo-northstar-manager"}
OTHER = {"X-Demo-Token": "demo-river-agent"}
CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
WRONG_CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c4"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'sportswear.db'}")) as c:
        yield c


def check(c, ticket="N-T3", line="N-L3", target="N-V-LEG-L", condition="unworn_with_tags"):
    return c.post(f"/tickets/{ticket}/exchange-check", headers=AGENT, json={
        "order_line_id": line, "target_variant_id": target, "item_condition": condition})


def propose(c, ticket="N-T3", line="N-L3", target="N-V-LEG-L", condition="unworn_with_tags", key="exchange-12345"):
    return c.post(f"/tickets/{ticket}/exchange-proposals", headers=AGENT, json={
        "order_line_id": line, "target_variant_id": target, "item_condition": condition,
        "reason": "Customer requested different leggings size after staff checked tags",
        "idempotency_key": key})


def test_catalog_contains_sportswear_products_and_sizes(client):
    data = client.get("/catalog", headers=AGENT).json()
    # RetailAI extends this original store with 10 extra products without
    # changing the original six sportswear fixtures or exchange workflow.
    assert len(data) == 16
    assert {"N-P-LEG", "N-P-TEE", "N-P-BRA", "N-P-SHORT", "N-P-SOCK", "N-P-MAT"}.issubset(
        {p["id"] for p in data})
    leggings = next(p for p in data if p["id"] == "N-P-LEG")
    assert {v["size"] for v in leggings["variants"]} == {"XS", "S", "M", "L", "XL"}
    assert next(v for v in leggings["variants"] if v["size"] == "L")["available_quantity"] == 12
    assert len(client.get("/catalog", headers=OTHER).json()) == 1


def test_exchange_intent_and_evidence(client):
    triage = client.post("/tickets/N-T3/triage", headers=AGENT).json()
    assert triage["intent"] == "exchanges"
    ctx = client.get("/tickets/N-T3/context", headers=AGENT).json()
    assert ctx["order"]["id"] == "N-1003"
    assert ctx["line_items"][0]["size"] == "M"
    assert ctx["policies"][0]["id"] == "N-EXCHANGES"
    assert ctx["policies"][0]["version"] == "demo-v2"
    assert ctx["shipments"][0]["status"] == "delivered"


def test_exchange_needs_condition_confirmation(client):
    data = check(client, condition="unknown").json()
    assert data["eligible_for_proposal"] is False
    assert data["checks"]["staff_condition_attested"] is False


def test_valid_exchange_preview(client):
    data = check(client).json()
    assert data["eligible_for_proposal"] is True
    assert all(data["checks"].values())
    assert data["evidence_policy"] == "N-EXCHANGES@demo-v2"


def test_exchange_outside_30_day_window(client):
    data = check(client, ticket="N-T4", line="N-L4").json()
    assert data["eligible_for_proposal"] is False
    assert data["checks"]["within_30_day_window"] is False
    assert propose(client, ticket="N-T4", line="N-L4").status_code == 422


def test_exchanges_must_remain_same_product(client):
    data = check(client, target="N-V-TEE-L").json()
    assert data["checks"]["same_product"] is False
    assert propose(client, target="N-V-TEE-L").status_code == 422


def test_out_of_stock_variant_blocked(client):
    data = check(client, target="N-V-LEG-XL").json()
    assert data["checks"]["stock_available"] is False


def test_cannot_exchange_same_original_variant(client):
    data = check(client, target="N-V-LEG-M").json()
    assert data["checks"]["different_variant"] is False


def test_final_sale_and_worn_items_blocked(client):
    final = check(client, ticket="N-T6", line="N-L6", target="N-V-SOCK-ONE").json()
    assert final["checks"]["not_final_sale"] is False
    worn = check(client, condition="worn_or_washed").json()
    assert worn["checks"]["staff_condition_attested"] is False
    assert propose(client, condition="worn_or_washed").status_code == 422


def test_cross_customer_line_denied(client):
    assert check(client, line="N-L4").status_code == 404
    assert propose(client, line="N-L4").status_code == 404


def test_cross_tenant_variant_and_ticket_denied(client):
    assert check(client, target="R-V-TEE-M").status_code == 404
    assert client.get("/orders/R-2001/tracking", headers=AGENT).status_code == 404
    assert client.post("/tickets/N-T3/exchange-check", headers=OTHER, json={
        "order_line_id": "N-L3", "target_variant_id": "N-V-LEG-L"}).status_code == 404


def confirm(client, action_id, token=CUSTOMER, target="N-V-LEG-L"):
    return client.post(f"/exchange-proposals/{action_id}/customer-confirm", headers=token,
                       json={"confirmed": True, "target_variant_id": target})


def approve(client, action_id):
    return client.post(f"/exchange-proposals/{action_id}/approve", headers=MANAGER)


def execute(client, action_id, token=MANAGER):
    return client.post(f"/exchange-proposals/{action_id}/execute-local", headers=token)


def large_stock(client):
    catalog = client.get("/catalog", headers=AGENT).json()
    leggings = next(p for p in catalog if p["id"] == "N-P-LEG")
    return next(v for v in leggings["variants"] if v["size"] == "L")["available_quantity"]


def test_exchange_confirmation_approval_and_local_inventory_reservation(client):
    first = propose(client)
    assert first.status_code == 201, first.text
    action_id = first.json()["id"]
    assert first.json()["status"] == "pending_customer_confirmation"
    assert execute(client, action_id).status_code == 409
    assert approve(client, action_id).status_code == 409
    assert confirm(client, action_id, token=AGENT).status_code == 403
    assert confirm(client, action_id, token=WRONG_CUSTOMER).status_code == 404
    assert confirm(client, action_id, target="N-V-LEG-S").status_code == 409
    assert confirm(client, action_id).status_code == 200
    assert confirm(client, action_id).status_code == 200
    assert client.post(f"/exchange-proposals/{action_id}/approve", headers=AGENT).status_code == 403
    approved = approve(client, action_id)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved_not_executed"
    assert approve(client, action_id).status_code == 409
    assert large_stock(client) == 12  # Approval alone never reserves stock.
    record_response = execute(client, action_id)
    assert record_response.status_code == 201, record_response.text
    record = record_response.json()
    assert record["status"] == "reserved_awaiting_return"
    assert record["source_variant_id"] == "N-V-LEG-M"
    assert record["target_variant_id"] == "N-V-LEG-L"
    assert record["quantity"] == 1
    assert large_stock(client) == 11
    assert execute(client, action_id).json()["id"] == record["id"]
    assert large_stock(client) == 11  # Retry cannot reserve twice.
    assert len(client.get("/orders/N-1003/exchanges", headers=AGENT).json()) == 1
    assert client.get("/tickets/N-T3", headers=AGENT).json()["status"] == "exchange_processing"
    assert client.get("/tickets/N-T3/context", headers=AGENT).json()["line_items"][0]["size"] == "M"
    assert propose(client, key="new-key-after-executed").status_code == 409
    audit = client.get("/audit-events", headers=MANAGER).json()
    assert any(x["event"] == "exchange_inventory_reserved_local" for x in audit)


def test_idempotency_and_duplicate_exchange_prevention(client):
    one = propose(client)
    assert one.status_code == 201
    two = propose(client)
    assert two.json()["id"] == one.json()["id"]
    assert propose(client, key="exchange-54321").status_code == 409
    assert propose(client, target="N-V-LEG-S").status_code == 409
    assert len(client.get("/exchange-proposals", headers=AGENT).json()) == 1


def test_missing_package_tracking_and_policy(client):
    assert client.post("/tickets/N-T5/triage", headers=AGENT).json()["intent"] == "missing_package"
    context = client.get("/tickets/N-T5/context", headers=AGENT).json()
    assert context["policies"][0]["id"] == "N-SHIPPING"
    track = client.get("/orders/N-1005/tracking", headers=AGENT).json()
    assert track[0]["status"] == "delivery_exception"
    assert track[0]["events"][-1]["status"] == "delivery_exception"


def test_audit_does_not_include_customer_message_text(client):
    propose(client)
    audit = client.get("/audit-events", headers=MANAGER).json()
    assert any(a["event"] == "exchange_proposed" for a in audit)
    assert "Customer requested different leggings" not in str(audit)
    assert client.get("/audit-events", headers=AGENT).status_code == 403


def test_customer_token_never_exposes_staff_inbox_or_orders(client):
    for url in ("/tickets", "/catalog", "/tickets/N-T3/context", "/orders/N-1003/exchanges",
                "/exchange-proposals", "/refund-proposals"):
        assert client.get(url, headers=CUSTOMER).status_code == 403, url
    assert client.post("/tickets/N-T3/triage", headers=CUSTOMER).status_code == 403
    assert client.get("/audit-events", headers=CUSTOMER).status_code == 403


def test_execute_requires_manager_approval(client):
    action_id = propose(client, key="confirm-gate-test").json()["id"]
    assert execute(client, action_id, token=AGENT).status_code == 403
    assert execute(client, action_id).status_code == 409
    assert confirm(client, action_id).status_code == 200
    assert execute(client, action_id).status_code == 409
    assert approve(client, action_id).status_code == 200
    assert execute(client, action_id, token=AGENT).status_code == 403
    assert large_stock(client) == 12


def test_execution_rolls_back_if_stock_changes_after_approval(client, tmp_path):
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import Session
    from app.models import ProductVariant
    action_id = propose(client, key="stock-vanished-demo").json()["id"]
    assert confirm(client, action_id).status_code == 200
    assert approve(client, action_id).status_code == 200
    engine = create_engine(f"sqlite:///{tmp_path / 'sportswear.db'}")
    with Session(engine) as db:
        db.execute(update(ProductVariant).where(ProductVariant.id == "N-V-LEG-L")
                   .values(available_quantity=0))
        db.commit()
    engine.dispose()
    assert execute(client, action_id).status_code == 409
    assert client.get("/orders/N-1003/exchanges", headers=AGENT).json() == []
    action = next(x for x in client.get("/exchange-proposals", headers=AGENT).json()
                  if x["id"] == action_id)
    assert action["status"] == "approved_not_executed"
    assert large_stock(client) == 0


def test_cross_tenant_cannot_confirm_or_execute(client):
    action_id = propose(client, key="tenant-gate-demo").json()["id"]
    river_customer = {"X-Demo-Token": "demo-river-customer-c1"}
    assert confirm(client, action_id, token=river_customer).status_code == 404
    assert client.post(f"/exchange-proposals/{action_id}/execute-local",
                       headers={"X-Demo-Token": "demo-river-manager"}).status_code == 404
    assert client.get("/orders/N-1003/exchanges", headers=OTHER).status_code == 404


def test_customer_confirmation_requires_literal_true(client):
    action_id = propose(client, key="literal-confirm-test").json()["id"]
    assert client.post(f"/exchange-proposals/{action_id}/customer-confirm", headers=CUSTOMER,
                       json={"confirmed": False, "target_variant_id": "N-V-LEG-L"}).status_code == 422
    assert approve(client, action_id).status_code == 409

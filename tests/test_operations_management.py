"""Management operations: synthetic-only, audited, versioned, tenant-scoped."""
from fastapi.testclient import TestClient
import pytest

from app.agent import SandboxModel
from app.main import create_app

STAFF = {"X-Demo-Token": "demo-northstar-agent"}
MANAGER = {"X-Demo-Token": "demo-northstar-manager"}
CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
RIVER_MANAGER = {"X-Demo-Token": "demo-river-manager"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path/'manage.db'}", agent_model=SandboxModel())) as c:
        yield c


def item(client, variant="N-V-HEELS-US8"):
    rows = client.get("/operations/manage/inventory", headers=STAFF).json()
    return next(v for v in rows if v["variant_id"] == variant)


def test_manager_role_required_to_change_stock_and_prices(client):
    old = item(client)
    payload = {"expected_available_quantity": old["available_quantity"],
               "new_available_quantity": old["available_quantity"] + 4,
               "expected_price_cents": old["price_cents"],
               "new_price_cents": old["price_cents"] + 500,
               "reason": "Synthetic stocktake correction"}
    path = "/operations/manage/variants/N-V-HEELS-US8"
    assert client.patch(path, json=payload).status_code == 401
    assert client.patch(path, json=payload, headers=CUSTOMER).status_code == 403
    assert client.patch(path, json=payload, headers=STAFF).status_code == 403
    assert client.patch(path, json=payload, headers=RIVER_MANAGER).status_code == 409
    done = client.patch(path, json=payload, headers=MANAGER)
    assert done.status_code == 200, done.text
    assert done.json()["available_quantity"] == old["available_quantity"] + 4
    assert done.json()["price_cents"] == old["price_cents"] + 500
    assert client.patch(path, json=payload, headers=MANAGER).status_code == 409
    a = client.get("/operations/insights", headers=STAFF).json()
    assert any(r["event"] == "inventory_manager_adjusted" for r in a["recent_audit"])


def test_invalid_stock_and_price_rejected(client):
    before = item(client)
    path = "/operations/manage/variants/N-V-HEELS-US8"
    original = {"expected_available_quantity": before["available_quantity"],
                "expected_price_cents": before["price_cents"],
                "reason": "Synthetic stocktake correction"}
    assert client.patch(path, headers=MANAGER, json={**original,
        "new_available_quantity": -1, "new_price_cents": before["price_cents"]}).status_code == 422
    assert client.patch(path, headers=MANAGER, json={**original,
        "new_available_quantity": before["available_quantity"], "new_price_cents": 0}).status_code == 422
    assert client.patch(path, headers=MANAGER, json={**original,
        "new_available_quantity": before["available_quantity"],
        "new_price_cents": before["price_cents"]}).status_code == 422
    assert item(client) == before


def test_product_details_persist_in_customer_catalog(client):
    before = item(client)
    payload = {"expected_title": before["product_title"], "expected_description": before["description"],
               "expected_exchangeable": before["exchangeable"], "title": "Mira Comfort Block Heels",
               "description": "Demo leather-look low block heels with cushioned footbed.",
               "exchangeable": False, "reason": "Synthetic product detail correction"}
    url = "/operations/manage/products/N-P-HEELS"
    assert client.patch(url, headers=STAFF, json=payload).status_code == 403
    changed = client.patch(url, headers=MANAGER, json=payload)
    assert changed.status_code == 200, changed.text
    assert changed.json()["exchangeable"] is False
    assert client.patch(url, headers=MANAGER, json=payload).status_code == 409
    customer = client.get("/customer/catalog", headers=CUSTOMER).json()
    updated = next(p for p in customer if p["id"] == "N-P-HEELS")
    assert updated["title"] == payload["title"]
    assert updated["exchangeable"] is False


def test_ticket_priority_assignment_and_status_with_version(client):
    url = "/operations/manage/tickets/N-T5"
    ticket = next(t for t in client.get("/operations/manage/tickets", headers=STAFF).json()
                  if t["id"] == "N-T5")
    assert ticket["priority"] == "normal" and ticket["version"] == 0
    payload = {"expected_status": ticket["status"], "expected_version": 0,
               "status": "escalated", "priority": "urgent", "assigned_to": "northstar-agent-1"}
    assert client.patch(url, headers=CUSTOMER, json=payload).status_code == 403
    result = client.patch(url, headers=STAFF, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "escalated"
    assert result.json()["version"] == 1
    assert result.json()["priority"] == "urgent"
    assert client.patch(url, headers=STAFF, json=payload).status_code == 409
    changed = result.json()
    result2 = client.patch(url, headers=STAFF, json={
        "expected_status": "escalated", "expected_version": changed["version"],
        "status": "in_progress", "priority": "high", "assigned_to": None})
    assert result2.status_code == 200, result2.text
    assert result2.json()["assigned_to"] is None and result2.json()["version"] == 2
    activity = client.get("/operations/manage/tickets/N-T5/activity", headers=STAFF).json()
    assert sum(e["event"] == "ticket_work_item_updated" for e in activity) == 2


def test_cross_tenant_assignment_and_workflow_protection(client):
    t = next(t for t in client.get("/operations/manage/tickets", headers=STAFF).json() if t["id"] == "N-T3")
    payload = {"expected_status": t["status"], "expected_version": 0,
               "status": t["status"], "priority": "high", "assigned_to": "river-agent-1"}
    assert client.patch("/operations/manage/tickets/N-T3", headers=STAFF, json=payload).status_code == 422
    assert client.patch("/operations/manage/tickets/N-T3", headers=RIVER_MANAGER, json=payload).status_code == 404
    payload["assigned_to"] = None
    payload["status"] = "exchange_processing"
    assert client.patch("/operations/manage/tickets/N-T3", headers=STAFF, json=payload).status_code == 422
    # A manager can adjust metadata, but cannot force protected exchange states through ticket management.
    payload["status"] = t["status"]
    assert client.patch("/operations/manage/tickets/N-T3", headers=STAFF, json=payload).status_code == 200


def test_ticket_and_inventory_visibility_follows_tenant_scope(client):
    for route in ("/operations/manage/tickets", "/operations/manage/inventory"):
        assert client.get(route).status_code == 401
        assert client.get(route, headers=CUSTOMER).status_code == 403
        assert client.get(route, headers=STAFF).status_code == 200
        assert client.get(route, headers=RIVER_MANAGER).status_code == 200
        assert len(client.get(route, headers=RIVER_MANAGER).json()) < len(client.get(route, headers=STAFF).json())


def test_pending_exchange_cannot_be_marked_resolved(client):
    # Fixture N-T3 does not initially have an exchange proposal; create one with
    # validated staff tool before attempting to override the status.
    checked = client.post("/tickets/N-T3/exchange-check", headers=STAFF, json={
        "order_line_id": "N-L3", "target_variant_id": "N-V-LEG-L",
        "item_condition": "unworn_with_tags"})
    assert checked.status_code == 200, checked.text
    assert checked.json()["eligible_for_proposal"] is True
    proposal = client.post("/tickets/N-T3/exchange-proposals", headers=STAFF, json={
        "order_line_id": "N-L3", "target_variant_id": "N-V-LEG-L",
        "item_condition": "unworn_with_tags", "reason": "Customer requested a size exchange",
        "idempotency_key": "ops-management-proposal-2026"})
    assert proposal.status_code == 201, proposal.text
    current = next(t for t in client.get("/operations/manage/tickets", headers=STAFF).json() if t["id"] == "N-T3")
    result = client.patch("/operations/manage/tickets/N-T3", headers=STAFF, json={
        "expected_status": current["status"], "expected_version": current["version"],
        "status": "resolved", "priority": "normal", "assigned_to": None})
    assert result.status_code == 409


def test_new_table_preserves_existing_ticket_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path/'persist.db'}"
    with TestClient(create_app(db_url, agent_model=SandboxModel())) as c:
        current = next(t for t in c.get("/operations/manage/tickets", headers=STAFF).json() if t["id"] == "N-T1")
        result = c.patch("/operations/manage/tickets/N-T1", headers=STAFF, json={
            "expected_status": current["status"], "expected_version": current["version"],
            "status": "in_progress", "priority": "high", "assigned_to": "northstar-agent-1"})
        assert result.status_code == 200, result.text
    with TestClient(create_app(db_url, agent_model=SandboxModel())) as c:
        stored = next(t for t in c.get("/operations/manage/tickets", headers=STAFF).json() if t["id"] == "N-T1")
        assert stored["priority"] == "high" and stored["assigned_to"] == "northstar-agent-1"
        assert stored["status"] == "in_progress"


def test_stale_stock_edit_rejected_after_customer_checkout(client):
    old = item(client)
    put = client.post("/customer/cart/items", headers=CUSTOMER, json={
        "variant_id": old["variant_id"], "quantity": 1,
        "idempotency_key": "management-stock-race-cart"})
    assert put.status_code == 200, put.text
    quote = client.get("/customer/checkout/preview", headers=CUSTOMER).json()["quote_token"]
    order = client.post("/customer/checkout/confirm", headers=CUSTOMER, json={
        "confirmed": True, "quote_token": quote,
        "idempotency_key": "management-stock-race-confirm"})
    assert order.status_code == 201, order.text
    after = item(client)
    assert after["available_quantity"] == old["available_quantity"] - 1
    attempt = client.patch(f"/operations/manage/variants/{old['variant_id']}", headers=MANAGER,
        json={"expected_available_quantity": old["available_quantity"],
              "new_available_quantity": 10,
              "expected_price_cents": old["price_cents"],
              "new_price_cents": old["price_cents"],
              "reason": "Old stocktake form became stale"})
    assert attempt.status_code == 409
    assert item(client)["available_quantity"] == after["available_quantity"]

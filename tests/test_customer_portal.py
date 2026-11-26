"""Synthetic customer/staff shared-state E2E contract, no live API or Shopify."""
import pytest
from fastapi.testclient import TestClient
from app.agent import SandboxModel
from app.main import create_app

CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
OTHER = {"X-Demo-Token": "demo-northstar-customer-c4"}
STAFF = {"X-Demo-Token": "demo-northstar-agent"}
MANAGER = {"X-Demo-Token": "demo-northstar-manager"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path/'customer.db'}", agent_model=SandboxModel())) as c:
        yield c


def submit(c, key="customer-duplicate-protect-01", target="N-V-LEG-L", confirmed=True, attested=True):
    return c.post("/customer/tickets/N-T3/exchange-request", headers=CUSTOMER, json={
        "order_line_id": "N-L3", "target_variant_id": target,
        "confirmed": confirmed, "condition_attested": attested,
        "idempotency_key": key})


def stock(c):
    products = c.get("/catalog", headers=STAFF).json()
    return next(v["available_quantity"] for p in products if p["id"] == "N-P-LEG"
                for v in p["variants"] if v["size"] == "L")


def test_customer_can_read_only_own_orders_and_tickets(client):
    assert [o["id"] for o in client.get("/customer/orders", headers=CUSTOMER).json()] == ["N-1003"]
    assert [t["id"] for t in client.get("/customer/tickets", headers=CUSTOMER).json()] == ["N-T3"]
    assert client.get("/customer/tickets/N-T1/context", headers=CUSTOMER).status_code == 404
    assert client.get("/customer/tickets/N-T3/context", headers=OTHER).status_code == 404
    assert client.get("/customer/tickets/N-T3/messages", headers=OTHER).status_code == 404
    assert client.get("/tickets", headers=CUSTOMER).status_code == 403
    assert client.get("/audit-events", headers=CUSTOMER).status_code == 403
    assert client.get("/customer/orders", headers=STAFF).status_code == 403


def test_customer_chat_uses_single_agent_without_write_tools(client):
    first = client.post("/customer/tickets/N-T3/chat", headers=CUSTOMER,
              json={"message": "I ordered medium leggings. Can I exchange them for large?"})
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["transaction_executed"] is False
    assert data["model_mode"] == "sandbox_scripted"
    history = client.get("/customer/tickets/N-T3/messages", headers=CUSTOMER).json()
    assert any(m["delivery_status"] == "customer_ai_response" for m in history)
    assert not any(m["delivery_status"] in ("agent_prompt", "agent_draft") for m in history)
    assert client.get("/exchange-proposals", headers=STAFF).json() == []
    assert stock(client) == 12
    assert client.post("/customer/tickets/N-T3/chat", headers=OTHER,
                json={"message": "Tell me about this order"}).status_code == 404


def test_customer_preview_does_not_allow_faking_staff_condition(client):
    preview = client.post("/customer/tickets/N-T3/exchange-preview", headers=CUSTOMER,
              json={"order_line_id": "N-L3", "target_variant_id": "N-V-LEG-L",
                    "item_condition": "unworn_with_tags"})
    assert preview.status_code == 200, preview.text
    assert preview.json()["checks"]["staff_condition_attested"] is False
    assert preview.json()["eligible_for_proposal"] is False


def test_customer_must_explicitly_confirm_and_attest(client):
    assert submit(client, confirmed=False).status_code == 422
    assert submit(client, attested=False).status_code == 422
    assert client.get("/exchange-proposals", headers=STAFF).json() == []


def test_customer_cannot_propose_cross_customer_or_unavailable_variants(client):
    assert submit(client, target="N-V-LEG-XL").status_code == 422
    attempt = client.post("/customer/tickets/N-T3/exchange-request", headers=OTHER,
           json={"order_line_id": "N-L3", "target_variant_id": "N-V-LEG-L",
                 "confirmed":True,"condition_attested":True,"idempotency_key":"other-customer-attempt"})
    assert attempt.status_code == 404
    wrong_line = client.post("/customer/tickets/N-T3/exchange-request", headers=CUSTOMER,
           json={"order_line_id": "N-L4", "target_variant_id": "N-V-LEG-L",
                 "confirmed":True,"condition_attested":True,"idempotency_key":"wrong-customer-line"})
    assert wrong_line.status_code == 404


def test_customer_to_staff_to_manager_shared_transaction(client):
    assert stock(client) == 12
    request = submit(client)
    assert request.status_code == 201, request.text
    r = request.json()
    assert r["status"] == "pending_staff_review"
    assert stock(client) == 12
    assert client.post(f"/exchange-proposals/{r['id']}/approve", headers=MANAGER).status_code == 409
    assert client.post(f"/exchange-proposals/{r['id']}/execute-local", headers=MANAGER).status_code == 409
    assert submit(client).json()["id"] == r["id"]
    assert client.post(f"/exchange-proposals/{r['id']}/verify-condition", headers=MANAGER,
                 json={"verified_unworn_with_tags":True}).status_code == 403
    assert client.post(f"/exchange-proposals/{r['id']}/verify-condition", headers=CUSTOMER,
                 json={"verified_unworn_with_tags":True}).status_code == 403
    verified = client.post(f"/exchange-proposals/{r['id']}/verify-condition", headers=STAFF,
                  json={"verified_unworn_with_tags":True})
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "pending_approval"
    approve = client.post(f"/exchange-proposals/{r['id']}/approve", headers=MANAGER)
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "approved_not_executed"
    reserved = client.post(f"/exchange-proposals/{r['id']}/execute-local", headers=MANAGER)
    assert reserved.status_code == 201, reserved.text
    assert reserved.json()["status"] == "reserved_awaiting_return"
    assert stock(client) == 11
    again = client.post(f"/exchange-proposals/{r['id']}/execute-local", headers=MANAGER)
    assert again.json()["id"] == reserved.json()["id"]
    assert stock(client) == 11
    status = client.get(f"/customer/exchange-requests/{r['id']}/status",headers=CUSTOMER).json()
    assert status["status"] == "inventory_reserved"
    assert status["record_reference"] == reserved.json()["id"]
    assert client.get(f"/customer/exchange-requests/{r['id']}/status",headers=OTHER).status_code == 404
    audit = client.get("/audit-events", headers=MANAGER).json()
    assert any(e["event"]=="customer_exchange_requested" for e in audit)
    assert any(e["event"]=="exchange_condition_staff_verified" for e in audit)


def test_staff_can_reject_condition_without_inventory_changes(client):
    req = submit(client).json()
    review = client.post(f"/exchange-proposals/{req['id']}/verify-condition", headers=STAFF,
                 json={"verified_unworn_with_tags":False})
    assert review.status_code==200
    assert review.json()["status"] == "rejected_condition"
    assert client.post(f"/exchange-proposals/{req['id']}/approve", headers=MANAGER).status_code==409
    assert stock(client)==12


def test_customer_ticket_creation_cannot_impersonate_other_customer(client):
    payload={"customer_id":"N-C4", "order_id":"N-1004", "subject":"Shipping question",
             "content":"Please check my package status"}
    assert client.post("/customer/tickets", headers=CUSTOMER,json=payload).status_code == 403
    payload.update(customer_id="N-C3", order_id="N-1004")
    assert client.post("/customer/tickets", headers=CUSTOMER,json=payload).status_code == 404
    payload["order_id"]="N-1003"
    created=client.post("/customer/tickets", headers=CUSTOMER,json=payload)
    assert created.status_code == 201
    assert created.json()["customer_id"]=="N-C3"
    assert client.get(f"/customer/tickets/{created.json()['id']}/messages", headers=CUSTOMER).status_code==200

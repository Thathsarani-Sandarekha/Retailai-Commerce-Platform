"""Checkout contracts: explicit confirmation, repricing, stock integrity and idempotency.

No real payment, Shopify orders or hosted Groq inference. Uses isolated SQLite.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agents.agent import SandboxModel
from app.customers.auth import Actor
from app.core.db import make_engine, make_session_factory
from app.main import create_app
from app.models import AuditEvent, CheckoutReceipt, Order, OrderLine, ProductVariant

C3 = {"X-Demo-Token": "demo-northstar-customer-c3"}
C4 = {"X-Demo-Token": "demo-northstar-customer-c4"}
RIVER = {"X-Demo-Token": "demo-river-customer-c1"}
STAFF = {"X-Demo-Token": "demo-northstar-agent"}
HEEL = "N-V-HEELS-US8"


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{tmp_path/'checkout.db'}"
    with TestClient(create_app(url, agent_model=SandboxModel())) as c:
        yield c, url


def add(c, qty=1, variant=HEEL, headers=C3, key="checkout-test-add-0001"):
    r = c.post("/customer/cart/items", headers=headers, json={
        "variant_id": variant, "quantity": qty, "idempotency_key": key})
    assert r.status_code == 200, r.text
    return r.json()


def preview(c, headers=C3):
    r = c.get("/customer/checkout/preview", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def confirm(c, token, key="checkout-confirm-key-0001", headers=C3, approved=True):
    return c.post("/customer/checkout/confirm", headers=headers, json={
        "confirmed": approved, "quote_token": token, "idempotency_key": key})


def variant_stock(url, variant_id=HEEL):
    engine = make_engine(url)
    with make_session_factory(engine)() as db:
        value = db.get(ProductVariant, variant_id).available_quantity
    engine.dispose()
    return value


def test_checkout_creates_real_unpaid_order_stock_audit_and_idempotency(client):
    c, url = client
    assert c.get("/customer/checkout/preview", headers=C3).status_code == 409
    assert c.get("/customer/checkout/preview", headers=STAFF).status_code == 403
    add(c, qty=2)
    p = preview(c)
    assert p["subtotal_cents"] == 13998
    assert p["total_cents"] == 13998
    assert p["payment_status"] == "not_charged"
    assert p["item_count"] == 2
    assert p["stock_reserved"] is False
    assert variant_stock(url) == 6
    assert confirm(c, p["quote_token"], approved=False).status_code == 422
    assert variant_stock(url) == 6
    r = confirm(c, p["quote_token"])
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "sandbox_order_created"
    assert data["payment_status"] == "not_charged"
    assert data["total_cents"] == 13998
    assert data["items"][0]["unit_price_cents"] == 6999
    assert variant_stock(url) == 4
    assert c.get("/customer/cart", headers=C3).json()["item_count"] == 0
    assert c.get("/customer/checkout/orders", headers=C3).json()[0]["order_id"] == data["order_id"]
    assert any(o["id"] == data["order_id"] for o in c.get("/customer/orders", headers=C3).json())
    engine = make_engine(url)
    with make_session_factory(engine)() as db:
        order = db.get(Order, data["order_id"])
        assert order.customer_id == "N-C3"
        assert order.refundable_cents == 0
        assert order.tracking_number is None
        assert order.fulfillment_status == "awaiting_payment_demo"
        lines = db.scalars(select(OrderLine).where(OrderLine.order_id == order.id)).all()
        assert len(lines) == 1 and lines[0].quantity == 2
        assert db.scalar(select(func.count()).select_from(CheckoutReceipt)) == 1
        events = db.scalars(select(AuditEvent).where(AuditEvent.event == "sandbox_checkout_confirmed")).all()
        assert len(events) == 1 and events[0].resource_id == order.id
    engine.dispose()
    again = confirm(c, p["quote_token"])
    assert again.status_code == 201 and again.json()["duplicate_request"] is True
    assert again.json()["order_id"] == data["order_id"]
    assert variant_stock(url) == 4
    assert confirm(c, "f" * 64).status_code == 409


def test_stale_quotes_out_of_stock_and_repricing_are_blocked(client):
    c, url = client
    add(c)
    old = preview(c)
    r = c.patch(f"/customer/cart/items/{HEEL}", headers=C3, json={"quantity": 2})
    assert r.status_code == 200
    stale = confirm(c, old["quote_token"])
    assert stale.status_code == 409
    assert "review" in stale.text.lower()
    assert variant_stock(url) == 6
    new = preview(c)
    engine = make_engine(url)
    with make_session_factory(engine)() as db:
        variant = db.get(ProductVariant, HEEL)
        variant.price_cents = 7500
        db.commit()
    engine.dispose()
    assert confirm(c, new["quote_token"]).status_code == 409
    assert variant_stock(url) == 6
    updated = preview(c)
    assert updated["total_cents"] == 15000
    engine = make_engine(url)
    with make_session_factory(engine)() as db:
        variant = db.get(ProductVariant, HEEL)
        variant.available_quantity = 1
        db.commit()
    engine.dispose()
    assert confirm(c, updated["quote_token"]).status_code == 409
    assert c.get("/customer/checkout/preview", headers=C3).status_code == 409
    assert c.get("/customer/cart", headers=C3).json()["item_count"] == 2


def test_customer_and_tenant_isolation_checkout(client):
    c, url = client
    add(c)
    mine = preview(c)
    for headers in (C4, RIVER, STAFF):
        assert c.get("/customer/checkout/orders", headers=headers).status_code in (200, 403)
        assert confirm(c, mine["quote_token"], headers=headers).status_code in (403, 409)
    assert variant_stock(url) == 6
    assert c.get("/customer/checkout/orders", headers=C4).json() == []
    assert confirm(c, mine["quote_token"]).status_code == 201
    assert c.get("/customer/checkout/orders", headers=C4).json() == []
    assert c.get("/customer/checkout/orders", headers=RIVER).json() == []


def test_two_items_rollback_entire_checkout_if_one_unavailable(client):
    c, url = client
    add(c, qty=1)
    add(c, qty=1, variant="N-V-LEG-L", key="checkout-test-add-0002")
    p = preview(c)
    engine = make_engine(url)
    with make_session_factory(engine)() as db:
        db.get(ProductVariant, "N-V-LEG-L").available_quantity = 0
        db.commit()
    engine.dispose()
    assert confirm(c, p["quote_token"]).status_code == 409
    assert variant_stock(url) == 6
    assert c.get("/customer/cart", headers=C3).json()["item_count"] == 2
    engine = make_engine(url)
    with make_session_factory(engine)() as db:
        assert db.scalar(select(func.count()).select_from(CheckoutReceipt)) == 0
        assert db.scalar(select(func.count()).select_from(Order).where(Order.id.like("RA-%"))) == 0
    engine.dispose()


def test_checkout_persists_across_application_restart(tmp_path):
    url = f"sqlite:///{tmp_path/'persist.db'}"
    with TestClient(create_app(url, agent_model=SandboxModel())) as c:
        add(c)
        p = preview(c)
        first = confirm(c, p["quote_token"]).json()
    with TestClient(create_app(url, agent_model=SandboxModel())) as c:
        again = confirm(c, p["quote_token"]).json()
        assert again["order_id"] == first["order_id"]
        assert again["duplicate_request"] is True
        assert c.get("/customer/checkout/orders", headers=C3).json()[0]["order_id"] == first["order_id"]
    assert variant_stock(url) == 5


def test_agent_prepares_cart_change_and_checkout_without_writing(client):
    c, url = client
    add(c)
    request = c.post("/customer/tickets/N-T3/chat", headers=C3,
                     json={"message": "Change quantity of the item in my cart to two"})
    assert request.status_code == 200, request.text
    data = request.json()
    assert [t["tool"] for t in data["tool_trace"]] == ["get_my_cart", "prepare_cart_change"]
    assert data["cart_proposal"]["action"] == "set_quantity"
    assert data["cart_proposal"]["quantity"] == 2
    assert c.get("/customer/cart", headers=C3).json()["item_count"] == 1
    request = c.post("/customer/tickets/N-T3/chat", headers=C3,
                     json={"message": "Help me checkout and place my order"})
    assert request.status_code == 200, request.text
    assert [t["tool"] for t in request.json()["tool_trace"]] == ["get_checkout_preview"]
    assert request.json()["transaction_executed"] is False
    assert c.get("/customer/checkout/orders", headers=C3).json() == []
    assert variant_stock(url) == 6


def test_cart_change_tool_cannot_skip_read_or_impersonate_customer(client):
    c, url = client
    add(c)
    from app.agents.agent import ToolExecution
    from app.core.db import make_session_factory
    from app.services import get_ticket
    engine = make_engine(url)
    with make_session_factory(engine)() as db:
        actor = Actor("northstar", "customer", "demo-c3", "N-C3")
        ticket = get_ticket(db, actor, "N-T3")
        tools = ToolExecution(db, actor, ticket)
        assert tools.call("prepare_cart_change", {"variant_id": HEEL, "quantity": 2})["error"] == "inspect_cart_and_select_variant_first"
        assert tools.call("get_my_cart", {})["item_count"] == 1
        assert tools.call("prepare_cart_change", {"variant_id": HEEL, "quantity": 8})["error"] == "insufficient_stock_or_cart_limit"
        proposed = tools.call("prepare_cart_change", {"variant_id": HEEL, "quantity": 0})
        assert proposed["action"] == "remove_item"
        assert db.scalar(select(func.count()).select_from(CheckoutReceipt)) == 0
        staff = Actor("northstar", "agent", "demo-staff")
        t2 = get_ticket(db, staff, "N-T3")
        stafftools = ToolExecution(db, staff, t2)
        assert stafftools.call("get_checkout_preview", {})["error"] == "customer_role_required"
        assert stafftools.call("prepare_cart_change", {"variant_id": HEEL, "quantity": 0})["error"] == "customer_role_required"
    engine.dispose()
    assert c.get("/customer/cart", headers=C3).json()["item_count"] == 1


def test_operations_dashboard_sees_confirmed_orders_not_other_tenants(client):
    c, _url = client
    assert c.get('/operations/sandbox-orders', headers=C3).status_code == 403
    assert c.get('/operations/sandbox-orders', headers=STAFF).json() == []
    add(c)
    placed = confirm(c, preview(c)['quote_token'])
    assert placed.status_code == 201
    staff_orders = c.get('/operations/sandbox-orders', headers=STAFF)
    assert staff_orders.status_code == 200
    row = staff_orders.json()[0]
    assert row['order_id'] == placed.json()['order_id']
    assert row['customer_id'] == 'N-C3'
    assert row['payment_status'] == 'not_charged'
    assert c.get('/operations/sandbox-orders', headers={
        'X-Demo-Token': 'demo-river-agent'}).json() == []

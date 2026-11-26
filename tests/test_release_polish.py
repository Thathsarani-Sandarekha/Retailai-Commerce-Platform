"""Regression coverage for no-charge demo payment and optional synthetic dashboard seed."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent import SandboxModel
from app.db import make_engine, make_session_factory
from app.main import create_app
from app.models import CheckoutReceipt, ProductVariant, Ticket
from scripts.seed_showcase_data import seed_showcase

C3 = {"X-Demo-Token": "demo-northstar-customer-c3"}
C4 = {"X-Demo-Token": "demo-northstar-customer-c4"}
RIVER = {"X-Demo-Token": "demo-river-customer-c1"}
STAFF = {"X-Demo-Token": "demo-northstar-agent"}


def _order(client):
    add = client.post("/customer/cart/items", headers=C3, json={
        "variant_id": "N-V-HEELS-US8", "quantity": 1,
        "idempotency_key": "release-polish-cart-add-001"})
    assert add.status_code == 200, add.text
    token = client.get("/customer/checkout/preview", headers=C3).json()["quote_token"]
    r = client.post("/customer/checkout/confirm", headers=C3, json={
        "confirmed": True, "quote_token": token,
        "idempotency_key": "release-polish-order-001"})
    assert r.status_code == 201, r.text
    return r.json()["order_id"]


def test_payment_is_confirmed_owned_and_idempotent(tmp_path):
    url = f"sqlite:///{tmp_path/'payment.db'}"
    with TestClient(create_app(url, agent_model=SandboxModel())) as c:
        order = _order(c)
        urlpath = f"/customer/checkout/orders/{order}/simulate-payment"
        assert c.post(urlpath, headers=C3, json={"confirmed": False}).status_code == 422
        assert c.post(urlpath, headers=C4, json={"confirmed": True}).status_code == 404
        assert c.post(urlpath, headers=RIVER, json={"confirmed": True}).status_code == 404
        assert c.post(urlpath, headers=STAFF, json={"confirmed": True}).status_code == 403
        good = c.post(urlpath, headers=C3, json={"confirmed": True})
        assert good.status_code == 200, good.text
        assert good.json()["payment_status"] == "simulated_paid"
        assert "no card" in good.json()["notice"].lower()
        repeated = c.post(urlpath, headers=C3, json={"confirmed": True})
        assert repeated.status_code == 200
        assert repeated.json()["duplicate_request"] is True
        orders = c.get("/customer/orders", headers=C3).json()
        assert next(o for o in orders if o["id"] == order)["status"] == "payment_simulated_demo"
        details = c.get("/operations/insights", headers=STAFF).json()
        assert details["metrics"]["demo_payments_simulated"] == 1
        assert next(o for o in details["recent_orders"] if o["order_id"] == order)["payment_status"] == "simulated_paid"
    engine = make_engine(url)
    with make_session_factory(engine)() as db:
        assert db.get(ProductVariant, "N-V-HEELS-US8").available_quantity == 5
    engine.dispose()


def test_showcase_seed_has_real_seven_day_activity_and_is_repeatable(tmp_path):
    url = f"sqlite:///{tmp_path/'showcase.db'}"
    with TestClient(create_app(url, agent_model=SandboxModel())) as c:
        engine = make_engine(url)
        with make_session_factory(engine)() as db:
            date = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
            a = seed_showcase(db, date)
            b = seed_showcase(db, date)
            assert a == {"tickets_added": sum((3,2,4,3,5,4,4)),
                         "demo_orders_added": sum((2,3,3,4,2,5,3))}
            assert b == {"tickets_added": 0, "demo_orders_added": 0}
            assert db.get(Ticket, "N-T3").subject.startswith("Leggings too small")
            assert db.scalar(select(CheckoutReceipt).where(CheckoutReceipt.id == "SHOW-R-001")) is not None
        engine.dispose()
        report = c.get("/operations/insights", headers=STAFF).json()
        # Current activity chart shows 7 days relative to runtime. Test data anchored to fixed date
        # but counts and customer/tenant access remain reproducible.
        assert report["metrics"]["sandbox_orders"] == sum((2,3,3,4,2,5,3))
        assert report["metrics"]["demo_payments_simulated"] == 7
        assert report["metrics"]["total_tickets"] >= 25
        assert len(report["ticket_intents"]) >= 4

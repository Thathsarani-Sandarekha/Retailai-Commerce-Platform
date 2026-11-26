"""Business operations dashboard contracts: real records and strict tenant isolation."""
from fastapi.testclient import TestClient
import pytest

from app.agent import SandboxModel
from app.main import create_app

STAFF = {"X-Demo-Token": "demo-northstar-agent"}
MANAGER = {"X-Demo-Token": "demo-northstar-manager"}
CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
RIVER = {"X-Demo-Token": "demo-river-agent"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path/'insights.db'}", agent_model=SandboxModel())) as c:
        yield c


def test_staff_and_manager_authorization_and_tenant_isolation(client):
    assert client.get("/operations/insights").status_code == 401
    assert client.get("/operations/insights", headers=CUSTOMER).status_code == 403
    a = client.get("/operations/insights", headers=STAFF)
    m = client.get("/operations/insights", headers=MANAGER)
    river = client.get("/operations/insights", headers=RIVER)
    assert a.status_code == 200 and m.status_code == 200 and river.status_code == 200
    north = a.json()
    other = river.json()
    assert north["environment"] == "synthetic_local_demo"
    assert north["metrics"]["total_tickets"] == 7
    assert north["metrics"]["catalog_products"] == 16
    assert north["metrics"]["sandbox_orders"] == 0
    assert north["metrics"]["sandbox_order_value_cents"] == 0
    assert north["metrics"]["out_of_stock_variants"] >= 1
    assert other["metrics"]["total_tickets"] == 1
    assert other["metrics"]["catalog_products"] == 1
    assert other["metrics"]["sandbox_orders"] == 0
    assert all(row["product_id"].startswith("N-") for row in north["inventory"])
    assert all(row["product_id"].startswith("R-") for row in other["inventory"])
    assert len(north["daily_activity"]) == 7
    assert m.json()["metrics"] == north["metrics"]


def test_real_checkout_updates_orders_value_and_inventory(client):
    initial = client.get("/operations/insights", headers=STAFF).json()
    before = next(v for v in initial["inventory"] if v["variant_id"] == "N-V-HEELS-US8")
    assert before["available_quantity"] == 6
    add = client.post("/customer/cart/items", headers=CUSTOMER, json={
        "variant_id": "N-V-HEELS-US8", "quantity": 2,
        "idempotency_key": "insights-cart-checkout-12345",
    })
    assert add.status_code == 200, add.text
    token = client.get("/customer/checkout/preview", headers=CUSTOMER).json()["quote_token"]
    placed = client.post("/customer/checkout/confirm", headers=CUSTOMER, json={
        "confirmed": True, "quote_token": token,
        "idempotency_key": "insights-confirm-checkout-12345",
    })
    assert placed.status_code == 201, placed.text
    record = placed.json()
    current = client.get("/operations/insights", headers=STAFF).json()
    assert current["metrics"]["sandbox_orders"] == 1
    assert current["metrics"]["sandbox_order_value_cents"] == 13998
    assert current["recent_orders"][0]["order_id"] == record["order_id"]
    assert current["recent_orders"][0]["payment_status"] == "not_charged"
    assert "not revenue" in current["payment_note"].lower()
    after = next(v for v in current["inventory"] if v["variant_id"] == "N-V-HEELS-US8")
    assert after["available_quantity"] == 4
    assert sum(day["demo_orders"] for day in current["daily_activity"]) == 1
    assert client.get("/operations/insights", headers=RIVER).json()["metrics"]["sandbox_orders"] == 0
    client.post("/customer/checkout/confirm", headers=CUSTOMER, json={
        "confirmed": True, "quote_token": token,
        "idempotency_key": "insights-confirm-checkout-12345",
    })
    assert client.get("/operations/insights", headers=STAFF).json()["metrics"]["sandbox_orders"] == 1


def test_agent_events_are_counted_without_exposing_messages(client):
    before = client.get("/operations/insights", headers=STAFF).json()["metrics"]
    response = client.post("/customer/tickets/N-T3/chat", headers=CUSTOMER,
        json={"message": "Can I exchange my leggings for a large?"})
    assert response.status_code == 200, response.text
    result = client.get("/operations/insights", headers=STAFF).json()
    assert result["metrics"]["ai_responses"] == before["ai_responses"] + 1
    assert result["metrics"]["tool_calls"] > before["tool_calls"]
    assert result["tool_summary"]
    serialized = str(result)
    assert "Can I exchange my leggings for a large?" not in serialized
    assert all("details" not in item for item in result["recent_audit"])
    assert all("body" not in item for item in result["recent_audit"])
    assert client.get("/operations/insights", headers=RIVER).json()["metrics"]["tool_calls"] == 0


def test_dashboard_route_is_wired_into_demo_proxy_and_sidebar():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    proxy = (root / "frontend/app/api/demo/[...path]/route.ts").read_text()
    sidebar = (root / "frontend/app/page.tsx").read_text()
    assert r"/^\/operations\/insights$/" in proxy
    assert 'href="/operations"' in sidebar
    assert (root / "frontend/app/operations/page.tsx").is_file()

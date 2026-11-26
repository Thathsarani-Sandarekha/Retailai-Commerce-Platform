"""budget-constraint, stock, authorization and tool-selection regressions."""
import json
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.agent import SandboxModel, ToolExecution
from app.auth import Actor
from app.db import make_engine, make_session_factory
from app.models import CartItem, Order, ProductVariant
from app.services import get_ticket

CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
STAFF = {"X-Demo-Token": "demo-northstar-agent"}
RIVER_CUSTOMER = {"X-Demo-Token": "demo-river-customer-c1"}


def request(occasion="evening", amount=22000, shoe_size="US 8"):
    return {"occasion": occasion, "budget_cents": amount,
            "clothing_size": "M", "shoe_size": shoe_size, "denim_size": "28"}


def client_for(tmp_path):
    return TestClient(create_app(f"sqlite:///{tmp_path/'style.db'}", agent_model=SandboxModel()))


def test_budget_engine_returns_real_stock_prices_and_complete_roles(tmp_path):
    with client_for(tmp_path) as client:
        response = client.post("/customer/style/budget", headers=CUSTOMER, json=request())
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["feasible"] is True
        assert {x["role"] for x in result["items"]} == {"main", "footwear", "bag", "accessory"}
        assert result["subtotal_cents"] == sum(x["price_cents"] for x in result["items"])
        assert result["subtotal_cents"] <= 22000
        assert result["remaining_cents"] == 22000 - result["subtotal_cents"]
        assert all(x["available_quantity"] > 0 for x in result["items"])
        assert all(x["size"] in ("M", "US 8", "ONE") for x in result["items"])
        assert result["cart_updated"] is False
        assert result["source"] == "synthetic_catalog"
        catalog = client.get("/customer/catalog", headers=CUSTOMER).json()
        actual_variants = {v["id"]: v for p in catalog for v in p["variants"]}
        for item in result["items"]:
            assert actual_variants[item["variant_id"]]["price_cents"] == item["price_cents"]
        assert client.get("/customer/cart", headers=CUSTOMER).json()["item_count"] == 0


def test_budget_too_small_no_false_complete_outfit(tmp_path):
    with client_for(tmp_path) as client:
        response = client.post("/customer/style/budget", headers=CUSTOMER, json=request(amount=12000))
        result = response.json()
        assert result["feasible"] is False
        assert result["items"] == []
        assert result["minimum_complete_cents"] > result["budget_cents"]
        assert result["shortfall_cents"] == result["minimum_complete_cents"] - result["budget_cents"]


def test_unavailable_size_does_not_suggest_sold_out_variant(tmp_path):
    with client_for(tmp_path) as client:
        result = client.post("/customer/style/budget", headers=CUSTOMER,
                             json=request(shoe_size="US 9")).json()
        assert result["feasible"] is False
        assert "footwear" in result["message"]


def test_each_occasion_has_complete_outfit_and_stays_in_budget(tmp_path):
    with client_for(tmp_path) as client:
        for occasion in ("casual", "office", "evening"):
            data = client.post("/customer/style/budget", headers=CUSTOMER,
                               json=request(occasion, 30000)).json()
            assert data["feasible"] is True, data
            assert data["subtotal_cents"] <= 30000
            assert len({x["role"] for x in data["items"]}) == len(data["items"])
            assert all(x["available_quantity"] > 0 for x in data["items"])


def test_customer_only_and_tenant_isolation(tmp_path):
    with client_for(tmp_path) as client:
        assert client.post("/customer/style/budget", json=request()).status_code == 401
        assert client.post("/customer/style/budget", headers=STAFF, json=request()).status_code == 403
        river = client.post("/customer/style/budget", headers=RIVER_CUSTOMER,
                            json=request()).json()
        assert river["feasible"] is False
        assert river["items"] == []


def test_pydantic_rejects_invalid_ranges_and_extra_parameters(tmp_path):
    with client_for(tmp_path) as client:
        for invalid in ({**request(), "budget_cents": -100},
                        {**request(), "occasion": "wedding"},
                        {**request(), "shoe_size": "US 99"},
                        {**request(), "tenant_id": "river"}):
            assert client.post("/customer/style/budget", headers=CUSTOMER,
                               json=invalid).status_code == 422


def test_outfit_reflects_current_stock_and_does_not_mutate_orders(tmp_path):
    db_path = tmp_path / "style.db"
    with client_for(tmp_path) as client:
        before = client.get("/customer/orders", headers=CUSTOMER).json()
        first = client.post("/customer/style/budget", headers=CUSTOMER, json=request()).json()
        assert first["feasible"]
        assert len(client.get("/customer/orders", headers=CUSTOMER).json()) == len(before)
    engine = make_engine(f"sqlite:///{db_path}")
    with make_session_factory(engine)() as db:
        heel = db.get(ProductVariant, "N-V-HEELS-US8")
        heel.available_quantity = 0
        db.commit()
    engine.dispose()
    with client_for(tmp_path) as client:
        second = client.post("/customer/style/budget", headers=CUSTOMER, json=request()).json()
        assert not second["feasible"]
        assert client.get("/customer/orders", headers=CUSTOMER).json() == before


def test_single_agent_styling_tool_is_customer_only_and_read_only(tmp_path):
    database = tmp_path / "tool.db"
    with TestClient(create_app(f"sqlite:///{database}", agent_model=SandboxModel())) as client:
        result = client.post("/customer/tickets/N-T3/chat", headers=CUSTOMER,
                    json={"message": "Build an evening outfit under $220"})
        assert result.status_code == 200, result.text
        payload = result.json()
        assert payload["tool_trace"] == [{"tool": "build_budget_outfit", "status": "ok"}]
        assert "$" in payload["reply"]
        assert payload["transaction_executed"] is False
        assert client.get("/customer/cart", headers=CUSTOMER).json()["item_count"] == 0
    engine = make_engine(f"sqlite:///{database}")
    with make_session_factory(engine)() as db:
        staff = Actor(tenant_id="northstar", role="agent", id="northstar-agent-1")
        ticket = get_ticket(db, staff, "N-T3")
        tools = ToolExecution(db, staff, ticket)
        assert tools.call("build_budget_outfit", request()) == {"error": "customer_role_required"}
        assert tools.call("build_budget_outfit", {**request(), "customer_id": "N-C4"}) == {"error": "invalid_tool_arguments"}
        assert db.scalars(select(CartItem)).all() == []
    engine.dispose()

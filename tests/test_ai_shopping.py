"""RetailAI shopping agent: deterministic provider double, real DB-backed business tools.

These tests prove the agent-to-cart boundary, not hosted-model accuracy.
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent import RetailSearchArgs, SandboxModel, ToolExecution
from app.auth import Actor
from app.main import create_app
from app.models import CartItem, CartMutation, ProductVariant
from app.services import get_ticket

CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
OTHER_CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c4"}
STAFF = {"X-Demo-Token": "demo-northstar-agent"}
OTHER_TENANT = {"X-Demo-Token": "demo-river-agent"}
PROMPT = "Find black heels in US size 8 under $100 and add one pair to my cart"


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path/'shopping.db'}", agent_model=SandboxModel())
    with TestClient(app) as c:
        yield c


def prepare(client):
    r = client.post("/customer/tickets/N-T3/chat", json={"message": PROMPT}, headers=CUSTOMER)
    assert r.status_code == 200, r.text
    return r.json()


def test_ai_prepares_confirmable_cart_suggestion_without_modifying_cart(client):
    before = client.get("/customer/cart", headers=CUSTOMER).json()
    assert before["item_count"] == 0
    result = prepare(client)
    assert result["model_mode"] == "sandbox_scripted"
    assert result["transaction_executed"] is False
    assert [x["tool"] for x in result["tool_trace"]] == ["search_retail_products", "prepare_cart_add"]
    assert all(x["status"] == "ok" for x in result["tool_trace"])
    proposal = result["cart_proposal"]
    assert proposal["variant_id"] == "N-V-HEELS-US8"
    assert proposal["quantity"] == 1
    assert proposal["unit_price_cents"] == 6999
    assert proposal["requires_customer_confirmation"] is True
    assert proposal["cart_updated"] is False
    assert "Nothing has been added" in result["reply"]
    assert client.get("/customer/cart", headers=CUSTOMER).json() == before
    # Message history contains a reply but no implicit cart mutation.
    assert client.get("/customer/tickets/N-T3/messages", headers=CUSTOMER).status_code == 200


def test_explicit_confirmation_adds_to_real_cart_exactly_once(client):
    proposal = prepare(client)["cart_proposal"]
    payload = {"variant_id": proposal["variant_id"], "quantity": proposal["quantity"],
               "idempotency_key": proposal["idempotency_key"]}
    first = client.post("/customer/cart/items", headers=CUSTOMER, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["subtotal_cents"] == 6999
    assert first.json()["item_count"] == 1
    repeat = client.post("/customer/cart/items", headers=CUSTOMER, json=payload)
    assert repeat.status_code == 200, repeat.text
    assert repeat.json() == first.json()
    assert client.get("/customer/cart", headers=CUSTOMER).json()["items"][0]["quantity"] == 1
    assert client.get("/customer/catalog", headers=CUSTOMER).json()
    # Cart additions never reserve catalog inventory.
    catalog = client.get("/customer/catalog", headers=CUSTOMER).json()
    heels = next(p for p in catalog if p["id"] == "N-P-HEELS")
    assert next(v for v in heels["variants"] if v["id"] == "N-V-HEELS-US8")["available_quantity"] == 6


def test_no_cart_changes_on_foreign_customer_and_staff_access(client):
    assert client.post("/customer/tickets/N-T3/chat", headers=OTHER_CUSTOMER,
        json={"message": PROMPT}).status_code == 404
    assert client.post("/customer/cart/items", headers=STAFF, json={
        "variant_id": "N-V-HEELS-US8", "quantity": 1,
        "idempotency_key": "another-actor-key-001"}).status_code == 403
    assert client.get("/customer/cart", headers=CUSTOMER).json()["item_count"] == 0


def test_tool_proposal_needs_search_result_and_customer_role(tmp_path):
    from app.db import Base, make_engine, make_session_factory
    from app.seed import seed_demo
    from app.retail_catalog import seed_retail_catalog
    engine = make_engine(f"sqlite:///{tmp_path/'tool.db'}")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as db:
        seed_demo(db)
        seed_retail_catalog(db)
        customer = Actor("northstar", "customer", "northstar-customer-c3", "N-C3")
        ticket = get_ticket(db, customer, "N-T3")
        tools = ToolExecution(db, customer, ticket)
        assert tools.call("prepare_cart_add", {"variant_id": "N-V-HEELS-US8", "quantity": 1}) == {
            "error": "search_and_select_variant_first"}
        args = {"query": "black heels", "category": "footwear", "size": "US 8",
                "color": "Black", "max_price_cents": 10000, "in_stock": True}
        matched = tools.call("search_retail_products", args)
        assert matched["count"] == 1
        assert matched["products"][0]["variants"][0]["variant_id"] == "N-V-HEELS-US8"
        assert tools.call("prepare_cart_add", {"variant_id": "R-V-TEE-M", "quantity": 1})["error"] == "search_and_select_variant_first"
        assert tools.call("prepare_cart_add", {"variant_id": "N-V-HEELS-US8", "quantity": 10})["error"] == "insufficient_stock_or_cart_limit"
        ready = tools.call("prepare_cart_add", {"variant_id": "N-V-HEELS-US8", "quantity": 1})
        assert ready["ready_for_confirmation"]
        assert tools.cart_proposal["cart_updated"] is False
        assert db.scalars(select(CartItem)).all() == []
        assert db.scalars(select(CartMutation)).all() == []
        staff = Actor("northstar", "agent", "northstar-agent-1")
        staff_tools = ToolExecution(db, staff, get_ticket(db, staff, "N-T3"))
        assert staff_tools.call("search_retail_products", args)["count"] == 1
        assert staff_tools.call("prepare_cart_add", {"variant_id": "N-V-HEELS-US8", "quantity": 1})["error"] == "customer_role_required"


def test_filtered_product_search_respects_price_and_stock(tmp_path):
    from app.db import Base, make_engine, make_session_factory
    from app.seed import seed_demo
    from app.retail_catalog import seed_retail_catalog
    engine = make_engine(f"sqlite:///{tmp_path/'search.db'}")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as db:
        seed_demo(db)
        seed_retail_catalog(db)
        actor = Actor("northstar", "customer", "northstar-customer-c3", "N-C3")
        tools = ToolExecution(db, actor, get_ticket(db, actor, "N-T3"))
        args = {"query": "heels", "category": "footwear", "size": "US 8",
                "color": "Black", "max_price_cents": 5000, "in_stock": True}
        assert tools.call("search_retail_products", args)["count"] == 0
        args["max_price_cents"] = 10000
        assert tools.call("search_retail_products", args)["count"] == 1
        args["size"] = "US 9"
        assert tools.call("search_retail_products", args)["count"] == 0  # out of stock
        args["in_stock"] = False
        assert tools.call("search_retail_products", args)["count"] == 1
        args["size"] = "US 8"
        args["color"] = "White"
        assert tools.call("search_retail_products", args)["count"] == 0


def test_agent_tool_schema_rejects_unknown_fields_and_untrusted_tenant(tmp_path):
    from app.db import Base, make_engine, make_session_factory
    from app.seed import seed_demo
    from app.retail_catalog import seed_retail_catalog
    engine = make_engine(f"sqlite:///{tmp_path/'invalid.db'}")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as db:
        seed_demo(db)
        seed_retail_catalog(db)
        actor = Actor("northstar", "customer", "northstar-customer-c3", "N-C3")
        tools = ToolExecution(db, actor, get_ticket(db, actor, "N-T3"))
        args = {"query": "heels", "category": "footwear", "size": "US 8",
                "color": "Black", "max_price_cents": 10000, "in_stock": True,
                "tenant_id": "river"}
        assert tools.call("search_retail_products", args)["error"] == "invalid_tool_arguments"
        assert tools.call("prepare_cart_add", {"variant_id": "N-V-HEELS-US8", "quantity": 1, "customer_id": "N-C4"})["error"] == "invalid_tool_arguments"
        assert db.scalars(select(CartItem)).all() == []


def test_read_only_cart_tool_is_customer_bound(client):
    before = client.get("/customer/cart", headers=CUSTOMER).json()
    reply = client.post("/customer/tickets/N-T3/chat", headers=CUSTOMER,
        json={"message": "What is in my cart?"})
    assert reply.status_code == 200, reply.text
    assert reply.json()["tool_trace"] == [{"tool": "get_my_cart", "status": "ok"}]
    assert reply.json()["cart_proposal"] is None
    assert "cart contains 0 item(s)" in reply.json()["reply"]
    assert client.get("/customer/cart", headers=CUSTOMER).json() == before

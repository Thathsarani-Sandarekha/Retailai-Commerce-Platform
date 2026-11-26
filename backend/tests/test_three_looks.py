"""exact anchor, three distinct outfits, real stock, safety and UI API contract."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.agent import SandboxModel, ToolExecution
from app.customers.auth import Actor
from app.core.db import make_engine, make_session_factory
from app.main import create_app
from app.models import CartItem, Order, ProductVariant
from app.services import get_ticket

CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
STAFF = {"X-Demo-Token": "demo-northstar-agent"}
RIVER = {"X-Demo-Token": "demo-river-customer-c1"}


def make_client(tmp_path):
    return TestClient(create_app(f"sqlite:///{tmp_path/'three.db'}", agent_model=SandboxModel()))


def payload(anchor="N-V-DENIM-28", budget=25000, owned=False):
    return {"anchor_variant_id": anchor, "budget_cents": budget,
            "clothing_size": "M", "shoe_size": "US 8", "denim_size": "28",
            "already_owned": owned}


def test_anchor_catalog_is_customer_only_and_reports_stock(tmp_path):
    with make_client(tmp_path) as c:
        anchors = c.get("/customer/style/anchors", headers=CUSTOMER)
        assert anchors.status_code == 200
        assert {x["product_id"] for x in anchors.json()} == {
            "N-P-DENIM", "N-P-SKIRT", "N-P-DRESS", "N-P-BLOUSE"}
        assert all(v["available_quantity"] >= 0 for item in anchors.json() for v in item["variants"])
        assert c.get("/customer/style/anchors", headers=STAFF).status_code == 403
        assert c.get("/customer/style/anchors").status_code == 401
        assert c.get("/customer/style/anchors", headers=RIVER).json() == []


def test_three_looks_same_variant_distinct_and_no_mutations(tmp_path):
    with make_client(tmp_path) as c:
        initial_cart = c.get("/customer/cart", headers=CUSTOMER).json()
        initial_orders = c.get("/customer/orders", headers=CUSTOMER).json()
        before_stock = {v["id"]: v["available_quantity"]
                        for p in c.get("/customer/catalog", headers=CUSTOMER).json()
                        for v in p["variants"]}
        response = c.post("/customer/style/three-looks", headers=CUSTOMER, json=payload())
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["feasible"] is True
        assert [l["occasion"] for l in data["looks"]] == ["casual", "office", "evening"]
        assert data["source"] == "synthetic_catalog"
        assert data["cart_updated"] is False
        assert len({tuple(i["variant_id"] for i in l["items"]) for l in data["looks"]}) == 3
        for look in data["looks"]:
            assert look["feasible"] is True
            assert [i["variant_id"] for i in look["items"]].count("N-V-DENIM-28") == 1
            assert look["outfit_value_cents"] == sum(i["price_cents"] for i in look["items"])
            assert look["to_buy_cents"] == look["outfit_value_cents"]
            assert look["to_buy_cents"] <= data["budget_cents"]
            assert all(i["available_quantity"] > 0 for i in look["items"])
            assert all(before_stock[i["variant_id"]] > 0 for i in look["items"])
        assert c.get("/customer/cart", headers=CUSTOMER).json() == initial_cart
        assert c.get("/customer/orders", headers=CUSTOMER).json() == initial_orders
        assert before_stock == {v["id"]: v["available_quantity"]
                        for p in c.get("/customer/catalog", headers=CUSTOMER).json()
                        for v in p["variants"]}


def test_three_anchor_choices_produce_three_looks(tmp_path):
    with make_client(tmp_path) as c:
        for anchor in ("N-V-DENIM-28", "N-V-SKIRT-M", "N-V-DRESS-M", "N-V-BLOUSE-M"):
            data = c.post("/customer/style/three-looks", headers=CUSTOMER,
                          json=payload(anchor=anchor, budget=30000)).json()
            assert data["feasible"], (anchor, data)
            assert len(data["looks"]) == 3
            assert all(l["items"][0]["variant_id"] == anchor for l in data["looks"])


def test_owned_anchor_excluded_from_purchase_budget(tmp_path):
    with make_client(tmp_path) as c:
        data = c.post("/customer/style/three-looks", headers=CUSTOMER,
                      json=payload(budget=20000, owned=True)).json()
        assert len(data["looks"]) == 3
        assert data["already_owned"] is True
        for look in data["looks"]:
            assert look["to_buy_cents"] == look["outfit_value_cents"] - 6499
            assert look["items"][0]["already_owned"] is True
            assert look["feasible"] is True


def test_small_budget_does_not_claim_outfit_is_affordable(tmp_path):
    with make_client(tmp_path) as c:
        data = c.post("/customer/style/three-looks", headers=CUSTOMER,
                      json=payload(budget=10000)).json()
        assert data["feasible"] is False
        assert any(not l["feasible"] and l["shortfall_cents"] > 0 for l in data["looks"])


def test_tenant_and_role_and_argument_validation(tmp_path):
    with make_client(tmp_path) as c:
        assert c.post("/customer/style/three-looks", json=payload()).status_code == 401
        assert c.post("/customer/style/three-looks", headers=STAFF, json=payload()).status_code == 403
        assert c.post("/customer/style/three-looks", headers=RIVER, json=payload()).json()["looks"] == []
        for bad in ({**payload(), "budget_cents": 0},
                    {**payload(), "anchor_variant_id": "R-V-TEE-M"},
                    {**payload(), "customer_id": "N-C4"},
                    {**payload(), "shoe_size": "US 12"}):
            resp = c.post("/customer/style/three-looks", headers=CUSTOMER, json=bad)
            if "anchor_variant_id" in bad and bad["anchor_variant_id"] == "R-V-TEE-M":
                assert resp.status_code == 200 and resp.json()["looks"] == []
            else:
                assert resp.status_code == 422


def test_sold_out_anchor_and_missing_required_stock(tmp_path):
    db_path = tmp_path / 'three.db'
    with make_client(tmp_path) as c:
        assert c.post("/customer/style/three-looks", headers=CUSTOMER, json=payload()).json()["feasible"]
    engine = make_engine(f"sqlite:///{db_path}")
    with make_session_factory(engine)() as db:
        variant = db.get(ProductVariant, "N-V-DENIM-28")
        variant.available_quantity = 0
        db.commit()
    with make_client(tmp_path) as c:
        assert c.post("/customer/style/three-looks", headers=CUSTOMER,
                      json=payload()).json()["reason"] == "anchor_out_of_stock"
        owned = c.post("/customer/style/three-looks", headers=CUSTOMER,
                      json=payload(owned=True)).json()
        assert owned["feasible"] is True
    engine.dispose()


def test_single_agent_tool_requires_prior_search_and_never_writes(tmp_path):
    database = tmp_path / 'three.db'
    with TestClient(create_app(f"sqlite:///{database}", agent_model=SandboxModel())) as client:
        resp = client.post("/customer/tickets/N-T3/chat", headers=CUSTOMER,
                           json={"message": "Show three looks with jeans"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert [x["tool"] for x in data["tool_trace"]] == ["search_retail_products", "build_three_looks"]
        assert data["transaction_executed"] is False
        assert client.get("/customer/cart", headers=CUSTOMER).json()["item_count"] == 0
    engine = make_engine(f"sqlite:///{database}")
    with make_session_factory(engine)() as db:
        staff = Actor(tenant_id="northstar", role="agent", id="northstar-agent-1")
        ticket = get_ticket(db, staff, "N-T3")
        tool = ToolExecution(db, staff, ticket)
        assert tool.call("build_three_looks", payload()) == {"error": "customer_role_required"}
        customer = Actor(tenant_id="northstar", role="customer", id="northstar-c3", customer_id="N-C3")
        customer_tool = ToolExecution(db, customer, ticket)
        assert customer_tool.call("build_three_looks", payload()) == {"error": "search_and_select_variant_first"}
        assert db.scalars(select(CartItem)).all() == []
    engine.dispose()

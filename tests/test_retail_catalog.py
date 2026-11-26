"""additive catalog and scoped product filters."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent import SandboxModel
from app.db import make_engine, make_session_factory
from app.main import create_app
from app.models import Product, ProductVariant
from app.retail_catalog import seed_retail_catalog

STAFF = {"X-Demo-Token": "demo-northstar-agent"}
CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
RIVER = {"X-Demo-Token": "demo-river-agent"}


def test_multicategory_catalog_is_shared_and_tenant_scoped(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path/'retail.db'}", agent_model=SandboxModel())) as client:
        staff = client.get("/catalog", headers=STAFF)
        customer = client.get("/customer/catalog", headers=CUSTOMER)
        assert staff.status_code == customer.status_code == 200
        assert len(staff.json()) == len(customer.json()) == 16
        categories = {p["category"] for p in staff.json()}
        assert {"footwear", "bags", "dresses", "tops", "bottoms", "skirts"} <= categories
        assert len(client.get("/catalog", headers=RIVER).json()) == 1
        assert client.get("/catalog", headers=CUSTOMER).status_code == 403
        assert client.get("/customer/catalog", headers=STAFF).status_code == 403


def test_price_size_color_and_stock_filters_use_real_variant_data(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path/'retail.db'}", agent_model=SandboxModel())) as client:
        params = {"q": "heels", "category": "footwear", "color": "black",
                  "size": "US 8", "max_price_cents": 7000, "in_stock": "true"}
        for route, role in (("/catalog", STAFF), ("/customer/catalog", CUSTOMER)):
            response = client.get(route, headers=role, params=params)
            assert response.status_code == 200, response.text
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == "N-P-HEELS"
            assert len(data[0]["variants"]) == 1
            assert data[0]["variants"][0]["size"] == "US 8"
            assert data[0]["variants"][0]["price_cents"] == 6999
            assert data[0]["variants"][0]["available_quantity"] == 6
        # Size US 9 is out of stock for the black heels, and cannot be offered.
        assert client.get("/customer/catalog", headers=CUSTOMER, params={
            "q": "heels", "size": "US 9", "in_stock": "true"}).json() == []
        # Demonstrate genuine negative / invalid price bounds.
        assert client.get("/catalog", headers=STAFF,
            params={"min_price_cents": 9000, "max_price_cents": 5000}).status_code == 422
        assert client.get("/catalog", headers=STAFF,
            params={"max_price_cents": -1}).status_code == 422
        # Searching for a literal SQL wildcard is not a "return everything" operation.
        assert client.get("/catalog", headers=STAFF, params={"q": "%"}).json() == []


def test_catalog_extension_is_idempotent_and_preserves_stock(tmp_path):
    url = f"sqlite:///{tmp_path/'existing.db'}"
    with TestClient(create_app(url, agent_model=SandboxModel())) as client:
        assert len(client.get("/catalog", headers=STAFF).json()) == 16
        assert client.get("/tickets/N-T3", headers=STAFF).status_code == 200
    engine = make_engine(url)
    Local = make_session_factory(engine)
    with Local() as session:
        heels = session.get(ProductVariant, "N-V-HEELS-US8")
        heels.available_quantity = 2
        session.commit()
        seed_retail_catalog(session)
        seed_retail_catalog(session)
        assert session.get(ProductVariant, "N-V-HEELS-US8").available_quantity == 2
        assert len(session.scalars(select(Product).where(Product.tenant_id == "northstar")).all()) == 16
    engine.dispose()
    with TestClient(create_app(url, agent_model=SandboxModel())) as client:
        heels = client.get("/catalog", headers=STAFF, params={"q": "heels"}).json()[0]
        assert next(v for v in heels["variants"] if v["size"] == "US 8")["available_quantity"] == 2
        assert client.get("/tickets/N-T3", headers=STAFF).status_code == 200

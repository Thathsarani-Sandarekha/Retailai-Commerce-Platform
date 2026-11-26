"""Shopify integration tests: no Shopify credentials or network required."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.agent import SandboxModel
from app.integrations.shopify import ShopifyAdapterError, ShopifyGraphQL
from app.main import create_app

STAFF = {"X-Demo-Token": "demo-northstar-agent"}
CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
RIVER = {"X-Demo-Token": "demo-river-agent"}


def test_local_adapter_is_tenant_scoped_and_staff_only(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOPIFY_ADAPTER", "local")
    with TestClient(create_app(f"sqlite:///{tmp_path/'shopify.db'}", agent_model=SandboxModel())) as api:
        assert api.get("/integrations/shopify/products").status_code == 401
        assert api.get("/integrations/shopify/products", headers=CUSTOMER).status_code == 403
        assert api.get("/integrations/shopify/orders", headers=CUSTOMER).status_code == 403
        result = api.get("/integrations/shopify/products", headers=STAFF, params={"limit": 25})
        assert result.status_code == 200
        assert result.json()["source"] == "local_sandbox"
        assert len(result.json()["products"]) == 16
        assert any(p["id"] == "N-P-HEELS" for p in result.json()["products"])
        assert len(api.get("/integrations/shopify/products", headers=RIVER).json()["products"]) == 1
        orders = api.get("/integrations/shopify/orders", headers=STAFF)
        assert orders.status_code == 200
        assert any(o["reference"] == "N-1003" for o in orders.json()["orders"])
        assert "customer_email" not in str(orders.json())
        assert api.get("/integrations/shopify/products", headers=STAFF, params={"limit": 50}).status_code == 422
        assert api.get("/integrations/shopify/status", headers=STAFF).json()["writes_enabled"] is False


def test_shopify_graphql_transport_and_normalization():
    def handler(request: httpx.Request):
        assert request.url.host == "demo-store.myshopify.com"
        assert request.url.path == "/admin/api/2026-10/graphql.json"
        assert request.headers["X-Shopify-Access-Token"] == "test-secret"
        body = json.loads(request.content)
        assert body["variables"] == {"first": 2}
        assert "mutation" not in body["query"].lower()
        if "RetailAIProducts" in body["query"]:
            return httpx.Response(200, json={"data": {"products": {
                "nodes": [{"id": "gid://shopify/Product/1", "title": "Test Tee", "handle": "test-tee",
                           "status": "ACTIVE", "variants": {"nodes": [{
                               "id": "gid://shopify/ProductVariant/7", "title": "M / Gray",
                               "sku": "TEE-M-G", "price": "29.95", "inventoryQuantity": 8}]}}],
                "pageInfo": {"hasNextPage": False, "endCursor": None}}}})
        return httpx.Response(200, json={"data": {"orders": {
            "nodes": [{"id": "gid://shopify/Order/99", "name": "#99",
                       "createdAt": "2026-11-19T10:00:00Z", "displayFulfillmentStatus": "FULFILLED",
                       "totalPriceSet": {"shopMoney": {"amount": "59.90", "currencyCode": "USD"}}}],
            "pageInfo": {"hasNextPage": False, "endCursor": None}}}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = ShopifyGraphQL("demo-store.myshopify.com", "test-secret", client=client)
        products = adapter.products(2)
        assert products["source"] == "shopify_graphql"
        assert products["products"][0]["variants"][0]["price_cents"] == 2995
        assert products["products"][0]["variants"][0]["available_quantity"] == 8
        orders = adapter.orders(2)
        assert orders["orders"][0]["total_cents"] == 5990
        assert orders["orders"][0]["reference"] == "#99"


def test_shopify_rejects_unsafe_store_domains_and_missing_credentials():
    for domain in ["evil.example.com", "demo.myshopify.com.evil.org", "localhost", "bad@demo.myshopify.com"]:
        with pytest.raises(ValueError):
            ShopifyGraphQL(domain, "token")
    with pytest.raises(ValueError):
        ShopifyGraphQL("demo.myshopify.com", "")
    with pytest.raises(ValueError):
        ShopifyGraphQL("demo.myshopify.com", "token", "beta")


@pytest.mark.parametrize("status,body,expected", [
    (429, {"errors": "details"}, "shopify_rate_limited"),
    (401, {"secret": "should_not_be_exposed"}, "shopify_auth_or_scope_failure"),
    (200, {"errors": [{"message": "secret diagnostic"}]}, "shopify_graphql_error"),
    (500, {"secret": "upstream private message"}, "shopify_http_failure"),
])
def test_shopify_failure_is_sanitized(status, body, expected):
    def handler(request: httpx.Request):
        return httpx.Response(status, json=body)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = ShopifyGraphQL("demo.myshopify.com", "test-secret", client=client)
        with pytest.raises(ShopifyAdapterError) as error:
            adapter.products(1)
        assert error.value.code == expected
        assert "secret" not in str(error.value)
        assert "diagnostic" not in str(error.value)


def test_shopify_mode_never_allows_cross_tenant_store_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOPIFY_ADAPTER", "shopify")
    monkeypatch.setenv("SHOPIFY_TENANT_ID", "northstar")
    monkeypatch.delenv("SHOPIFY_ADMIN_ACCESS_TOKEN", raising=False)
    with TestClient(create_app(f"sqlite:///{tmp_path/'shopify.db'}", agent_model=SandboxModel())) as api:
        cross = api.get("/integrations/shopify/products", headers=RIVER)
        assert cross.status_code == 403
        assert cross.json()["detail"] == "shopify_store_not_configured_for_tenant"
        own = api.get("/integrations/shopify/products", headers=STAFF)
        assert own.status_code == 503
        assert own.json()["detail"] == "shopify_configuration_invalid"


def test_live_api_route_uses_fixed_authorized_store(tmp_path, monkeypatch):
    """Exercise FastAPI -> configured adapter path without contacting Shopify."""
    from app.integrations import shopify

    monkeypatch.setenv("SHOPIFY_ADAPTER", "shopify")
    monkeypatch.setenv("SHOPIFY_TENANT_ID", "northstar")
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "demo.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "test-secret")
    monkeypatch.setenv("SHOPIFY_API_VERSION", "2026-10")

    class FakeShopify:
        def __init__(self, domain, token, api_version):
            assert (domain, token, api_version) == ("demo.myshopify.com", "test-secret", "2026-10")

        def products(self, limit):
            return {"source": "shopify_graphql", "products": [{"id": "gid://shopify/Product/1"}],
                    "page_info": {"hasNextPage": False}}

        def orders(self, limit):
            return {"source": "shopify_graphql", "orders": [{"id": "gid://shopify/Order/1"}],
                    "page_info": {"hasNextPage": False}}

    monkeypatch.setattr(shopify, "ShopifyGraphQL", FakeShopify)
    with TestClient(create_app(f"sqlite:///{tmp_path/'shopify.db'}", agent_model=SandboxModel())) as api:
        result = api.get("/integrations/shopify/products", headers=STAFF)
        assert result.status_code == 200
        assert result.json()["source"] == "shopify_graphql"
        assert api.get("/integrations/shopify/orders", headers=STAFF).json()["orders"][0]["id"].startswith("gid://")
        assert api.get("/integrations/shopify/products", headers=CUSTOMER).status_code == 403
        assert api.get("/integrations/shopify/products", headers=RIVER).status_code == 403
        assert api.get("/integrations/shopify/status", headers=STAFF).json()["writes_enabled"] is False

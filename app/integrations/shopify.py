"""Read-only Shopify Admin GraphQL adapter with a deterministic local fallback.

This adapter is used by staff-only integration endpoints, not by customer chat.
It deliberately never performs a Shopify mutation, nor silently fails over
from a live-shop request to local data (which would hide failed integrations).
"""
from __future__ import annotations

import os
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Actor, authenticate_staff
from ..models import Order, Product, ProductVariant

_ALLOWED_DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.myshopify\.com$")
_ALLOWED_VERSION = re.compile(r"^20\d{2}-(?:01|04|07|10)$")

# Only known queries are executable. Neither user messages nor request params
# may supply arbitrary GraphQL operations or a Shopify store URL.
_PRODUCTS_QUERY = """query RetailAIProducts($first: Int!) {
  products(first: $first) {
    nodes {
      id title handle status
      variants(first: 25) {
        nodes { id title sku price inventoryQuantity }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""

_ORDERS_QUERY = """query RetailAIOrders($first: Int!) {
  orders(first: $first) {
    nodes {
      id name createdAt displayFulfillmentStatus
      totalPriceSet { shopMoney { amount currencyCode } }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""


def _as_cents(amount: str | int | float | Decimal) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class ShopifyAdapterError(Exception):
    """Sanitized integration failure without raw Shopify payload or credentials."""

    def __init__(self, code: str, status: int = 502):
        self.code, self.status = code, status
        super().__init__(code)


class ShopifyGraphQL:
    """Minimal verified read adapter; access tokens are provided externally."""

    def __init__(self, domain: str, token: str, api_version: str = "2026-10",
                 client: httpx.Client | None = None):
        if not _ALLOWED_DOMAIN.fullmatch(domain):
            raise ValueError("Shopify store must be a valid *.myshopify.com domain")
        if not _ALLOWED_VERSION.fullmatch(api_version):
            raise ValueError("Invalid Shopify API version")
        if not token or not token.strip():
            raise ValueError("Shopify access token required for Shopify mode")
        self.url = f"https://{domain}/admin/api/{api_version}/graphql.json"
        self.token = token
        self.client = client

    def _request(self, operation: str, variables: dict[str, Any]) -> dict[str, Any]:
        if operation == "products":
            query = _PRODUCTS_QUERY
        elif operation == "orders":
            query = _ORDERS_QUERY
        else:
            raise ValueError("Unsupported Shopify query")
        headers = {"X-Shopify-Access-Token": self.token, "Content-Type": "application/json"}
        try:
            if self.client is None:
                with httpx.Client(timeout=12.0, follow_redirects=False) as client:
                    response = client.post(self.url, json={"query": query, "variables": variables}, headers=headers)
            else:
                response = self.client.post(self.url, json={"query": query, "variables": variables}, headers=headers)
        except httpx.TimeoutException as exc:
            raise ShopifyAdapterError("shopify_timeout", 504) from exc
        except httpx.RequestError as exc:
            raise ShopifyAdapterError("shopify_unreachable", 502) from exc
        if response.status_code == 429:
            raise ShopifyAdapterError("shopify_rate_limited", 503)
        if response.status_code in (401, 403):
            raise ShopifyAdapterError("shopify_auth_or_scope_failure", 502)
        if not 200 <= response.status_code < 300:
            raise ShopifyAdapterError("shopify_http_failure", 502)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ShopifyAdapterError("shopify_invalid_json", 502) from exc
        if not isinstance(payload, dict) or payload.get("errors") or not isinstance(payload.get("data"), dict):
            raise ShopifyAdapterError("shopify_graphql_error", 502)
        return payload["data"]

    def products(self, limit: int) -> dict[str, Any]:
        data = self._request("products", {"first": limit})
        connection = data.get("products") or {}
        rows = []
        for item in connection.get("nodes") or []:
            rows.append({
                "id": item["id"], "title": item["title"], "handle": item.get("handle"),
                "status": item.get("status"),
                "variants": [{
                    "id": v["id"], "title": v.get("title"), "sku": v.get("sku"),
                    "price_cents": _as_cents(v["price"]),
                    "available_quantity": v.get("inventoryQuantity"),
                } for v in ((item.get("variants") or {}).get("nodes") or [])],
            })
        return {"source": "shopify_graphql", "products": rows,
                "page_info": connection.get("pageInfo") or {"hasNextPage": False, "endCursor": None}}

    def orders(self, limit: int) -> dict[str, Any]:
        data = self._request("orders", {"first": limit})
        connection = data.get("orders") or {}
        rows = []
        for order in connection.get("nodes") or []:
            money = ((order.get("totalPriceSet") or {}).get("shopMoney") or {})
            rows.append({"id": order["id"], "reference": order.get("name"),
                         "fulfillment_status": order.get("displayFulfillmentStatus"),
                         "placed_at": order.get("createdAt"),
                         "total_cents": _as_cents(money["amount"]), "currency": money.get("currencyCode")})
        return {"source": "shopify_graphql", "orders": rows,
                "page_info": connection.get("pageInfo") or {"hasNextPage": False, "endCursor": None}}


class LocalShopifySandbox:
    """Maps existing RetailAI SQLAlchemy data into the same read shapes."""

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def products(self, limit: int) -> dict[str, Any]:
        products = self.db.scalars(select(Product).where(Product.tenant_id == self.tenant_id)
                                   .order_by(Product.title).limit(limit)).all()
        rows = []
        for product in products:
            variants = self.db.scalars(select(ProductVariant).where(
                ProductVariant.tenant_id == self.tenant_id, ProductVariant.product_id == product.id)
                .order_by(ProductVariant.id)).all()
            rows.append({"id": product.id, "title": product.title, "handle": None,
                         "status": "DEMO", "variants": [{
                             "id": v.id, "title": f"{v.color} / {v.size}", "sku": v.sku,
                             "price_cents": v.price_cents, "available_quantity": v.available_quantity,
                         } for v in variants]})
        return {"source": "local_sandbox", "products": rows,
                "page_info": {"hasNextPage": False, "endCursor": None}}

    def orders(self, limit: int) -> dict[str, Any]:
        orders = self.db.scalars(select(Order).where(Order.tenant_id == self.tenant_id)
                                 .order_by(Order.placed_at.desc()).limit(limit)).all()
        return {"source": "local_sandbox", "orders": [{
            "id": o.id, "reference": o.id, "fulfillment_status": o.fulfillment_status,
            "placed_at": o.placed_at.isoformat() if o.placed_at else None,
            "total_cents": o.total_cents, "currency": o.currency,
        } for o in orders], "page_info": {"hasNextPage": False, "endCursor": None}}


def adapter_mode() -> str:
    mode = os.getenv("SHOPIFY_ADAPTER", "local").lower().strip()
    if mode not in {"local", "shopify"}:
        raise ShopifyAdapterError("invalid_shopify_adapter_mode", 503)
    return mode


def resolve_adapter(db: Session, tenant_id: str) -> ShopifyGraphQL | LocalShopifySandbox:
    if adapter_mode() == "local":
        return LocalShopifySandbox(db, tenant_id)
    # Do not allow tenant selection through any caller-controlled query or header.
    assigned_tenant = os.getenv("SHOPIFY_TENANT_ID", "")
    if not assigned_tenant or assigned_tenant != tenant_id:
        raise ShopifyAdapterError("shopify_store_not_configured_for_tenant", 403)
    try:
        return ShopifyGraphQL(
            os.getenv("SHOPIFY_STORE_DOMAIN", ""),
            os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN", ""),
            os.getenv("SHOPIFY_API_VERSION", "2026-10"),
        )
    except ValueError as exc:
        raise ShopifyAdapterError("shopify_configuration_invalid", 503) from exc


def mount_shopify_routes(app: FastAPI, db_session):
    """Opt-in staff-only integration preview; existing commerce routes untouched."""

    @app.get("/integrations/shopify/status", tags=["Shopify integration"])
    def status(actor: Actor = Depends(authenticate_staff)):
        mode = adapter_mode()
        allowed = mode == "local" or os.getenv("SHOPIFY_TENANT_ID") == actor.tenant_id
        return {"adapter": mode, "tenant_configured": allowed, "writes_enabled": False,
                "api_version": os.getenv("SHOPIFY_API_VERSION", "2026-10") if mode == "shopify" else None}

    @app.get("/integrations/shopify/products", tags=["Shopify integration"])
    def products(limit: int = Query(10, ge=1, le=25), actor: Actor = Depends(authenticate_staff),
                 db: Session = Depends(db_session)):
        try:
            return resolve_adapter(db, actor.tenant_id).products(limit)
        except ShopifyAdapterError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from exc

    @app.get("/integrations/shopify/orders", tags=["Shopify integration"])
    def orders(limit: int = Query(10, ge=1, le=25), actor: Actor = Depends(authenticate_staff),
               db: Session = Depends(db_session)):
        try:
            return resolve_adapter(db, actor.tenant_id).orders(limit)
        except ShopifyAdapterError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from exc

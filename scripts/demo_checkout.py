"""Reproducible checkout demo in an isolated temporary database; no real payments/keys.

Run: python -m scripts.demo_checkout
"""
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.agent import SandboxModel
from app.main import create_app

CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
STAFF = {"X-Demo-Token": "demo-northstar-agent"}


def main():
    with TemporaryDirectory(prefix="retailai_checkout_") as d:
        url = f"sqlite:///{Path(d) / 'shop.db'}"
        with TestClient(create_app(url, agent_model=SandboxModel())) as c:
            catalog = c.get("/customer/catalog", headers=CUSTOMER).json()
            heel = next(p for p in catalog if p["id"] == "N-P-HEELS")
            before = next(v for v in heel["variants"] if v["id"] == "N-V-HEELS-US8")
            added = c.post("/customer/cart/items", headers=CUSTOMER, json={
                "variant_id": before["id"], "quantity": 2,
                "idempotency_key": "checkout-walkthrough-add-0001"})
            assert added.status_code == 200, added.text
            quote = c.get("/customer/checkout/preview", headers=CUSTOMER)
            assert quote.status_code == 200, quote.text
            p = quote.json()
            print("SYNTHETIC CHECKOUT")
            print("Cart preview:", p["item_count"], "items; total $", f"{p['total_cents']/100:.2f}")
            print("Stock before confirmation:", before["available_quantity"])
            refused = c.post("/customer/checkout/confirm", headers=CUSTOMER, json={
                "quote_token": p["quote_token"], "confirmed": False,
                "idempotency_key": "checkout-walkthrough-order-0001"})
            assert refused.status_code == 422
            print("Without customer confirmation: BLOCKED")
            payload = {"quote_token": p["quote_token"], "confirmed": True,
                       "idempotency_key": "checkout-walkthrough-order-0001"}
            r = c.post("/customer/checkout/confirm", headers=CUSTOMER, json=payload)
            assert r.status_code == 201, r.text
            o = r.json()
            assert o["payment_status"] == "not_charged"
            print("Created local order:", o["order_id"], "ref:", o["reference"])
            print("Payment:", o["payment_status"], "| Status:", o["status"])
            again = c.post("/customer/checkout/confirm", headers=CUSTOMER, json=payload)
            assert again.json()["duplicate_request"] is True
            assert again.json()["order_id"] == o["order_id"]
            print("Duplicate request: returned same order")
            catalog = c.get("/customer/catalog", headers=CUSTOMER).json()
            heel_after = next(p for p in catalog if p["id"] == "N-P-HEELS")
            after = next(v for v in heel_after["variants"] if v["id"] == "N-V-HEELS-US8")
            print("Stock after confirmation:", after["available_quantity"])
            assert after["available_quantity"] == before["available_quantity"] - 2
            assert c.get("/customer/cart", headers=CUSTOMER).json()["item_count"] == 0
            staff_view = c.get("/operations/sandbox-orders", headers=STAFF).json()
            assert staff_view[0]["order_id"] == o["order_id"]
            print("Staff dashboard order visible:", staff_view[0]["order_id"])
            print("PASS: atomic local order; no real charge, Shopify call or shipment")


if __name__ == "__main__":
    main()

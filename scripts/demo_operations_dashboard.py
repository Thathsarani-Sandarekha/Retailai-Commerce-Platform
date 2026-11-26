"""Isolated proof of operational metrics; never mutates your configured demo database."""
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent import SandboxModel
from app.main import create_app


STAFF = {"X-Demo-Token": "demo-northstar-agent"}
CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}


def main():
    with tempfile.TemporaryDirectory() as directory:
        url = f"sqlite:///{Path(directory) / 'operations-demo.db'}"
        with TestClient(create_app(url, agent_model=SandboxModel())) as client:
            before = client.get("/operations/insights", headers=STAFF).json()
            print("BEFORE | demo orders:", before["metrics"]["sandbox_orders"],
                  "| unpaid order value (cents):", before["metrics"]["sandbox_order_value_cents"])
            payload = {"variant_id": "N-V-HEELS-US8", "quantity": 2,
                       "idempotency_key": "operations-demo-cart-add-1234"}
            res = client.post("/customer/cart/items", headers=CUSTOMER, json=payload)
            assert res.status_code == 200, res.text
            quote = client.get("/customer/checkout/preview", headers=CUSTOMER).json()
            check = {"confirmed": True, "quote_token": quote["quote_token"],
                     "idempotency_key": "operations-demo-checkout-1234"}
            res = client.post("/customer/checkout/confirm", headers=CUSTOMER, json=check)
            assert res.status_code == 201, res.text
            after = client.get("/operations/insights", headers=STAFF).json()
            stock = next(v for v in after["inventory"] if v["variant_id"] == "N-V-HEELS-US8")
            assert after["metrics"]["sandbox_orders"] == 1
            assert after["metrics"]["sandbox_order_value_cents"] == 13998
            assert stock["available_quantity"] == 4
            assert after["recent_orders"][0]["order_id"] == res.json()["order_id"]
            print("AFTER  | demo orders:", after["metrics"]["sandbox_orders"],
                  "| unpaid order value (cents):", after["metrics"]["sandbox_order_value_cents"])
            print("STOCK  | US8 black heels:", stock["available_quantity"])
            print("PAYMENT | not_charged, no real revenue")
            print("PASS: real local checkout record drives business metrics, no live provider")


if __name__ == "__main__":
    main()

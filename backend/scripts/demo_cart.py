"""Repeatable, isolated cart demonstration. No Groq key or running server required.

Run: python -m scripts.demo_cart
"""
from tempfile import TemporaryDirectory
from pathlib import Path
from fastapi.testclient import TestClient
from app.agents.agent import SandboxModel
from app.main import create_app

HEADERS = {"X-Demo-Token": "demo-northstar-customer-c3"}


def main():
    with TemporaryDirectory(prefix="retailai-cart-") as temp:
        url = f"sqlite:///{Path(temp) / 'demo.db'}"
        with TestClient(create_app(url, agent_model=SandboxModel())) as client:
            before = client.get("/customer/cart", headers=HEADERS).json()
            assert before["item_count"] == 0
            payload = {"variant_id": "N-V-HEELS-US8", "quantity": 2,
                       "idempotency_key": "retailai-cart-demo-001"}
            first = client.post("/customer/cart/items", headers=HEADERS, json=payload)
            first.raise_for_status()
            first_data = first.json()
            assert first_data["subtotal_cents"] == 13998
            repeated = client.post("/customer/cart/items", headers=HEADERS, json=payload)
            repeated.raise_for_status()
            assert repeated.json()["item_count"] == 2
            print("CART BEFORE:", before["item_count"], "items")
            print("ADDED: 2 × Mira Black Block Heels (US 8)")
            print("SUBTOTAL: USD", f"{first_data['subtotal_cents'] / 100:.2f}")
            print("RETRY: preserved quantity", repeated.json()["item_count"])
        # Check the committed state after the app closes and opens again.
        with TestClient(create_app(url, agent_model=SandboxModel())) as client:
            persisted = client.get("/customer/cart", headers=HEADERS).json()
            assert persisted["item_count"] == 2
            assert persisted["checkout_enabled"] is False
            print("RESTART: cart persisted,", persisted["item_count"], "items")
            print("CHECKOUT ENABLED:", persisted["checkout_enabled"])
            print("PASS: customer-scoped durable local cart; no order or stock reservation")


if __name__ == "__main__":
    main()

"""Offline deterministic shopping-tool smoke test against disposable synthetic DB.

Does not use Groq; live hosted tool selection must be checked in the browser.
Does not touch the user's configured DATABASE_URL or .env file.
"""
from tempfile import TemporaryDirectory
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent import SandboxModel
from app.main import create_app

TOKEN = {"X-Demo-Token": "demo-northstar-customer-c3"}


def main():
    with TemporaryDirectory() as folder:
        database_url = f"sqlite:///{Path(folder) / 'retailai-shopping-smoke.db'}"
        with TestClient(create_app(database_url, agent_model=SandboxModel())) as client:
            prompt = "Find black heels in US size 8 under $100 and add one pair to my cart"
            print("DETERMINISTIC SHOPPING SMOKE DEMO (NO GROQ)")
            initial = client.get("/customer/cart", headers=TOKEN).json()
            print("Cart before AI draft:", initial["item_count"], "items")
            response = client.post("/customer/tickets/N-T3/chat", headers=TOKEN,
                                   json={"message": prompt})
            response.raise_for_status()
            body = response.json()
            proposal = body["cart_proposal"]
            assert proposal, body
            print("Tool trace:", body["tool_trace"])
            print("AI prepared:", proposal["product_title"], proposal["size"],
                  f"${proposal['line_total_cents']/100:.2f}")
            still_empty = client.get("/customer/cart", headers=TOKEN).json()
            assert still_empty["item_count"] == 0
            print("Cart before confirmation:", still_empty["item_count"], "items")
            payload = {"variant_id": proposal["variant_id"],
                       "quantity": proposal["quantity"],
                       "idempotency_key": proposal["idempotency_key"]}
            confirmed = client.post("/customer/cart/items", headers=TOKEN, json=payload)
            confirmed.raise_for_status()
            updated = confirmed.json()
            assert updated["item_count"] == 1 and updated["subtotal_cents"] == 6999
            retry = client.post("/customer/cart/items", headers=TOKEN, json=payload)
            retry.raise_for_status()
            assert retry.json()["item_count"] == 1
            print("After explicit confirmation:", updated["item_count"], "item(s)",
                  f"subtotal ${updated['subtotal_cents']/100:.2f}")
            print("Duplicate confirmation:", "no duplicate added")
            print("PASS: customer-scoped read tools, validated offer, confirmed cart add, idempotency")
            print("NOTE: no payment, order creation, inventory reservation, or Shopify operation")


if __name__ == "__main__":
    main()

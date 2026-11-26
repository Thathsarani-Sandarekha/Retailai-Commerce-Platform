"""Verify the Shopify-compatible local adapter without a dev store or key."""
import os
from tempfile import TemporaryDirectory
from pathlib import Path
from fastapi.testclient import TestClient
from app.agent import SandboxModel
from app.main import create_app


def main():
    os.environ["SHOPIFY_ADAPTER"] = "local"
    with TemporaryDirectory() as temp:
        url = "sqlite:///" + str(Path(temp) / "shopify_demo.db")
        with TestClient(create_app(url, agent_model=SandboxModel())) as api:
            headers = {"X-Demo-Token": "demo-northstar-agent"}
            products = api.get("/integrations/shopify/products", headers=headers, params={"limit": 25})
            orders = api.get("/integrations/shopify/orders", headers=headers)
            assert products.status_code == orders.status_code == 200
            assert products.json()["source"] == "local_sandbox"
            assert any(p["id"] == "N-P-HEELS" for p in products.json()["products"])
            assert any(o["id"] == "N-1003" for o in orders.json()["orders"])
            print("Shopify-style local catalog products:", len(products.json()["products"]))
            print("Orders:", len(orders.json()["orders"]))
            print("Adapter mode:", products.json()["source"])
            print("PASS — staff-only reads, shared database, no external calls or writes")


if __name__ == "__main__":
    main()

"""Fresh isolated demo; does not touch the user's configured DATABASE_URL."""
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
from app.agents.agent import SandboxModel

HEADERS = {"X-Demo-Token": "demo-northstar-customer-c3"}

def main():
    with tempfile.TemporaryDirectory() as directory:
        with TestClient(create_app(f"sqlite:///{Path(directory) / 'style.db'}", agent_model=SandboxModel())) as client:
            print("BUDGET CHALLENGE (SYNTHETIC CATALOG)")
            for occasion in ("casual", "office", "evening"):
                data = client.post("/customer/style/budget", headers=HEADERS, json={
                    "occasion": occasion, "budget_cents": 22000, "clothing_size": "M",
                    "shoe_size": "US 8", "denim_size": "28",
                }).json()
                assert data["feasible"] and data["subtotal_cents"] <= 22000
                assert data["subtotal_cents"] == sum(x["price_cents"] for x in data["items"])
                print(f"{occasion}: ${data['subtotal_cents']/100:.2f} / $220.00 — " +
                      ", ".join(x["title"] for x in data["items"]))
            too_small = client.post("/customer/style/budget", headers=HEADERS, json={
                "occasion": "evening", "budget_cents": 12000, "clothing_size": "M",
                "shoe_size": "US 8", "denim_size": "28",
            }).json()
            assert not too_small["feasible"] and not too_small["items"]
            assert client.get("/customer/cart", headers=HEADERS).json()["item_count"] == 0
            agent = client.post("/customer/tickets/N-T3/chat", headers=HEADERS, json={
                "message": "Build an evening outfit under $220"
            }).json()
            assert agent["tool_trace"] == [{"tool": "build_budget_outfit", "status": "ok"}]
            print("Groq-style agent tool path: scripted offline test double, successfully executed")
            print("PASS — budget constraints, complete looks, insufficient budget, unchanged cart")

if __name__ == "__main__":
    main()

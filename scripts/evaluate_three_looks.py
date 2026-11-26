"""Synthetic regression grid for anchor consistency, budgets and no-cart mutation."""
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.agent import SandboxModel
from app.main import create_app


def main():
    anchors = ["N-V-DENIM-28", "N-V-SKIRT-M", "N-V-DRESS-M", "N-V-BLOUSE-M"]
    budgets = [12000, 20000, 30000]
    checked = valid = feasible = 0
    with TemporaryDirectory(prefix="retailai-three-looks-eval-") as folder:
        with TestClient(create_app(f"sqlite:///{Path(folder)/'eval.db'}", agent_model=SandboxModel())) as client:
            headers = {"X-Demo-Token": "demo-northstar-customer-c3"}
            cart_before = client.get("/customer/cart", headers=headers).json()
            for anchor in anchors:
                for budget in budgets:
                    for owned in (False, True):
                        payload = {"anchor_variant_id": anchor, "budget_cents": budget,
                                   "clothing_size": "M", "shoe_size": "US 8",
                                   "denim_size": "28", "already_owned": owned}
                        response = client.post("/customer/style/three-looks", headers=headers, json=payload)
                        assert response.status_code == 200, response.text
                        result = response.json()
                        assert len(result["looks"]) == 3
                        for look in result["looks"]:
                            checked += 1
                            if look["feasible"]:
                                feasible += 1
                            rows = look["items"]
                            consistency = bool(rows) and rows[0]["variant_id"] == anchor
                            consistency &= len({x["variant_id"] for x in rows}) == len(rows)
                            consistency &= look["to_buy_cents"] == sum(
                                x["price_cents"] for x in rows if not x["already_owned"])
                            consistency &= look["outfit_value_cents"] == sum(x["price_cents"] for x in rows)
                            consistency &= look["feasible"] == (look["to_buy_cents"] <= budget)
                            consistency &= all(x["available_quantity"] > 0 or x["already_owned"] for x in rows)
                            assert consistency, (anchor, budget, owned, look)
                            valid += 1
            assert client.get("/customer/cart", headers=headers).json() == cart_before
    print(f"Cases: {len(anchors)*len(budgets)*2}, outfits evaluated: {checked}")
    print(f"Constraint/price/anchor invariants: {valid}/{checked} passed")
    print(f"Affordable complete looks: {feasible}/{checked} (varies by demo budget)")
    print("Read-only cart integrity: PASS")
    print("Synthetic fixtures only; this is not a learned styling-relevance evaluation.")


if __name__ == "__main__":
    main()

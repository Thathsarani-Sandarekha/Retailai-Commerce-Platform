"""Reproducible synthetic budget-constraint audit (not a model relevance benchmark)."""
import json
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
from app.agent import SandboxModel

HEADERS = {"X-Demo-Token": "demo-northstar-customer-c3"}

def main():
    with tempfile.TemporaryDirectory() as directory:
        with TestClient(create_app(f"sqlite:///{Path(directory) / 'evaluation.db'}", agent_model=SandboxModel())) as client:
            tested = feasible = invalid_complete = out_of_budget = 0
            for occasion in ("casual", "office", "evening"):
                for budget in (10000, 12000, 15000, 18000, 22000, 30000):
                    for shoe_size in ("US 7", "US 8", "US 9"):
                        payload = {"occasion": occasion, "budget_cents": budget,
                                   "clothing_size": "M", "shoe_size": shoe_size, "denim_size": "28"}
                        response = client.post("/customer/style/budget", headers=HEADERS, json=payload)
                        assert response.status_code == 200
                        result = response.json()
                        tested += 1
                        if result["feasible"]:
                            feasible += 1
                            if not result["items"] or any(x["available_quantity"] <= 0 for x in result["items"]):
                                invalid_complete += 1
                            if result["subtotal_cents"] != sum(x["price_cents"] for x in result["items"]):
                                invalid_complete += 1
                            if result["subtotal_cents"] > budget:
                                out_of_budget += 1
                        elif result["items"]:
                            invalid_complete += 1
            report = {"dataset": "synthetic catalog 16 items; 54 scenario grid",
                      "total_scenarios": tested, "feasible_scenarios": feasible,
                      "invalid_outfit_scenarios": invalid_complete,
                      "over_budget_scenarios": out_of_budget,
                      "constraint_compliance": (tested-invalid_complete-out_of_budget)/tested,
                      "limitations": "Deterministic synthetic tests; not fashion relevance, live Groq, or real-customer outcome evidence"}
            print(json.dumps(report, indent=2))
            assert not invalid_complete and not out_of_budget

if __name__ == "__main__":
    main()

"""Run the read-only One Item, Three Looks demo with a disposable database."""
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.agent import SandboxModel
from app.main import create_app


def main():
    with TemporaryDirectory(prefix="retailai-three-looks-") as folder:
        with TestClient(create_app(f"sqlite:///{Path(folder)/'demo.db'}", agent_model=SandboxModel())) as client:
            headers = {"X-Demo-Token": "demo-northstar-customer-c3"}
            payload = {"anchor_variant_id": "N-V-DENIM-28", "budget_cents": 25000,
                       "clothing_size": "M", "shoe_size": "US 8", "denim_size": "28",
                       "already_owned": False}
            before = client.get("/customer/cart", headers=headers).json()
            result = client.post("/customer/style/three-looks", headers=headers, json=payload)
            result.raise_for_status()
            data = result.json()
            print("ONE ITEM, THREE LOOKS")
            print("Selected hero:", data["anchor"]["title"], data["anchor"]["size"])
            for look in data["looks"]:
                print(f"{look['occasion'].upper():8}  ${look['to_buy_cents']/100:.2f}  "
                      f"budget_ok={look['feasible']}  "
                      + " + ".join(row["title"] for row in look["items"]))
            assert len(data["looks"]) == 3 and all(look["feasible"] for look in data["looks"])
            assert all(look["items"][0]["variant_id"] == payload["anchor_variant_id"]
                       for look in data["looks"])
            assert client.get("/customer/cart", headers=headers).json() == before
            print("PASS: Same exact variant in three distinct looks; no cart changed.")


if __name__ == "__main__":
    main()

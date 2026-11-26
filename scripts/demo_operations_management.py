"""Isolated manager/staff workflow; never modifies the user's configured DB."""
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from app.agent import SandboxModel
from app.main import create_app


def main():
    manager = {"X-Demo-Token": "demo-northstar-manager"}
    staff = {"X-Demo-Token": "demo-northstar-agent"}
    with TemporaryDirectory(prefix="retailai-manage-") as temp:
        url = "sqlite:///" + str(Path(temp) / "retailai-management.db").replace("\\", "/")
        with TestClient(create_app(url, agent_model=SandboxModel())) as api:
            variants = api.get("/operations/manage/inventory", headers=staff).json()
            heel = next(p for p in variants if p["variant_id"] == "N-V-HEELS-US8")
            print("BEFORE stock:", heel["available_quantity"], "price:", heel["price_cents"])
            changed = api.patch(f"/operations/manage/variants/{heel['variant_id']}", headers=manager,
                                json={"expected_available_quantity": heel["available_quantity"],
                                      "new_available_quantity": heel["available_quantity"] + 3,
                                      "expected_price_cents": heel["price_cents"],
                                      "new_price_cents": heel["price_cents"],
                                      "reason": "Demo receiving inventory stocktake"})
            assert changed.status_code == 200, changed.text
            assert changed.json()["available_quantity"] == heel["available_quantity"] + 3
            replay = api.patch(f"/operations/manage/variants/{heel['variant_id']}", headers=manager,
                               json={"expected_available_quantity": heel["available_quantity"],
                                     "new_available_quantity": heel["available_quantity"] + 3,
                                     "expected_price_cents": heel["price_cents"],
                                     "new_price_cents": heel["price_cents"],
                                     "reason": "Demo receiving inventory stocktake"})
            assert replay.status_code == 409
            ticket = next(t for t in api.get("/operations/manage/tickets", headers=staff).json() if t["id"] == "N-T5")
            assigned = api.patch("/operations/manage/tickets/N-T5", headers=staff, json={
                "expected_status": ticket["status"], "expected_version": ticket["version"],
                "status": "escalated", "priority": "urgent", "assigned_to": "northstar-manager-1"})
            assert assigned.status_code == 200, assigned.text
            assert assigned.json()["priority"] == "urgent"
            print("AFTER stock:", changed.json()["available_quantity"])
            print("TICKET N-T5:", assigned.json()["status"], "·", assigned.json()["priority"],
                  "·", assigned.json()["assigned_to"])
            print("PASS: manager edit, stale update rejection, staff assignment, persisted state")
            print("NOTE: isolated synthetic database. No Shopify or customer data changed.")


if __name__ == "__main__":
    main()

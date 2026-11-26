"""Integration contract for UI actions, using a temporary synthetic DB.

This validates the backend operations the Next.js UI calls. It does not claim
browser E2E tests or live Groq verification.
"""
from fastapi.testclient import TestClient
from app.main import create_app
from app.agents.agent import SandboxModel

STAFF = {"X-Demo-Token": "demo-northstar-agent"}
MANAGER = {"X-Demo-Token": "demo-northstar-manager"}
CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}


def test_ui_support_and_exchange_journey(tmp_path):
    app = create_app(f"sqlite:///{tmp_path/'ui-contract.db'}", agent_model=SandboxModel())
    with TestClient(app) as client:
        for path in ("/health", "/tickets", "/catalog", "/analytics/overview",
                     "/exchange-proposals", "/tickets/N-T3/context", "/tickets/N-T3/messages",
                     "/orders/N-1003/exchanges"):
            assert client.get(path, headers=STAFF).status_code == 200, path
        catalog = client.get("/catalog", headers=STAFF).json()
        leggings = next(p for p in catalog if p["id"] == "N-P-LEG")
        size_l = next(v for v in leggings["variants"] if v["size"] == "L")
        assert size_l["available_quantity"] == 12

        draft = client.post("/tickets/N-T3/agent/chat", headers=STAFF,
                            json={"message": "Check medium to large leggings exchange"})
        assert draft.status_code == 200, draft.text
        assert draft.json()["transaction_executed"] is False

        preview = {"order_line_id": "N-L3", "target_variant_id": "N-V-LEG-L",
                   "item_condition": "unworn_with_tags"}
        checked = client.post("/tickets/N-T3/exchange-check", headers=STAFF, json=preview)
        assert checked.status_code == 200, checked.text
        assert checked.json()["eligible_for_proposal"] is True

        created = client.post("/tickets/N-T3/exchange-proposals", headers=STAFF, json={
            **preview, "reason": "Customer requested size M to L exchange; demo condition attested",
            "idempotency_key": "stage3-ui-contract-n-t3-leg-l",
        })
        assert created.status_code == 201, created.text
        action_id = created.json()["id"]
        assert created.json()["status"] == "pending_customer_confirmation"
        assert client.post(f"/exchange-proposals/{action_id}/approve", headers=MANAGER).status_code == 409

        consent = client.post(f"/exchange-proposals/{action_id}/customer-confirm", headers=CUSTOMER,
                              json={"confirmed": True, "target_variant_id": "N-V-LEG-L"})
        assert consent.status_code == 200, consent.text
        approved = client.post(f"/exchange-proposals/{action_id}/approve", headers=MANAGER)
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved_not_executed"
        reserved = client.post(f"/exchange-proposals/{action_id}/execute-local", headers=MANAGER)
        assert reserved.status_code == 201, reserved.text
        assert reserved.json()["status"] == "reserved_awaiting_return"
        duplicate = client.post(f"/exchange-proposals/{action_id}/execute-local", headers=MANAGER)
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == reserved.json()["id"]
        catalog_after = client.get("/catalog", headers=STAFF).json()
        leggings_after = next(p for p in catalog_after if p["id"] == "N-P-LEG")
        assert next(v for v in leggings_after["variants"] if v["size"] == "L")["available_quantity"] == 11
        records = client.get("/orders/N-1003/exchanges", headers=STAFF).json()
        assert len(records) == 1

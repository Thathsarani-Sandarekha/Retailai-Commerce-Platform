"""Repeatable local API walkthrough. Run after starting uvicorn on an UNUSED synthetic DB."""
import argparse
from uuid import uuid4
import httpx

AGENT = {"X-Demo-Token": "demo-northstar-agent"}
MANAGER = {"X-Demo-Token": "demo-northstar-manager"}
CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=20.0) as client:
        def call(method, path, headers, data=None):
            response = client.request(method, path, headers=headers, json=data)
            if response.is_error:
                raise RuntimeError(f"{method} {path}: {response.status_code} {response.text}")
            return response.json()

        def stock():
            products = call("GET", "/catalog", AGENT)
            leggings = next(p for p in products if p["id"] == "N-P-LEG")
            return next(v["available_quantity"] for v in leggings["variants"]
                        if v["id"] == "N-V-LEG-L")

        before = stock()
        print(f"BEFORE: Northstar size-L leggings available = {before}")
        check = call("POST", "/tickets/N-T3/exchange-check", AGENT, {
            "order_line_id": "N-L3", "target_variant_id": "N-V-LEG-L",
            "item_condition": "unworn_with_tags"})
        assert check["eligible_for_proposal"], check
        print(f"Policy: {check['evidence_policy']}; eligible for proposal: yes")
        proposal = call("POST", "/tickets/N-T3/exchange-proposals", AGENT, {
            "order_line_id": "N-L3", "target_variant_id": "N-V-LEG-L",
            "item_condition": "unworn_with_tags",
            "reason": "Customer requested large; staff verified unworn item with tags",
            "idempotency_key": f"northstar-demo-{uuid4().hex}"})
        action_id = proposal["id"]
        print(f"Proposal: {action_id} -> {proposal['status']}")
        confirmed = call("POST", f"/exchange-proposals/{action_id}/customer-confirm", CUSTOMER, {
            "confirmed": True, "target_variant_id": "N-V-LEG-L"})
        print(f"Confirmed by synthetic customer: {confirmed['customer_id']}")
        approved = call("POST", f"/exchange-proposals/{action_id}/approve", MANAGER)
        print(f"Manager approval: {approved['status']}")
        record = call("POST", f"/exchange-proposals/{action_id}/execute-local", MANAGER)
        print(f"Local exchange record: {record['id']} -> {record['status']}")
        replay = call("POST", f"/exchange-proposals/{action_id}/execute-local", MANAGER)
        after = stock()
        records = call("GET", "/orders/N-1003/exchanges", AGENT)
        assert replay["id"] == record["id"]
        assert after == before - 1
        assert sum(r["id"] == record["id"] for r in records) == 1
        print(f"AFTER: Northstar size-L leggings available = {after}")
        print("PASS: durable local exchange record, inventory reserved exactly once.")
        print("NOTE: No Shopify mutation, return receipt, refund, or shipment occurred.")


if __name__ == "__main__":
    main()

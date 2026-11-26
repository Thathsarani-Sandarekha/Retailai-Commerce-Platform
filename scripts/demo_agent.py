"""Read-only agent demo. Start uvicorn, then python -m scripts.demo_agent.

Intentionally DOES NOT propose, confirm, approve or execute an exchange.
Run python -m scripts.demo_exchange to show the separately gated local write.
"""
import argparse
import httpx

TOKEN = {"X-Demo-Token": "demo-northstar-agent"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=60.0) as client:
        before = client.get("/catalog", headers=TOKEN)
        before.raise_for_status()
        before_stock = next(v["available_quantity"] for p in before.json()
                            if p["id"] == "N-P-LEG" for v in p["variants"] if v["size"] == "L")
        response = client.post("/tickets/N-T3/agent/chat", headers=TOKEN,
            json={"message": "Help the customer exchange their medium leggings for size large."})
        response.raise_for_status()
        result = response.json()
        after = client.get("/catalog", headers=TOKEN)
        after.raise_for_status()
        after_stock = next(v["available_quantity"] for p in after.json()
                           if p["id"] == "N-P-LEG" for v in p["variants"] if v["size"] == "L")
        print("MODEL MODE:", result["model_mode"])
        print("GRAPH ENGINE:", result["graph_engine"])
        print("TOOLS:", result["tool_trace"])
        print("DRAFT RESPONSE:\n", result["draft"])
        print("BEFORE STOCK:", before_stock, "AFTER AGENT DRAFT:", after_stock)
        assert before_stock == after_stock
        assert result["sent_to_customer"] is False
        assert result["transaction_executed"] is False
        print("PASS: tools called, no exchange created or stock reserved by the agent.")
        print("NEXT: python -m scripts.demo_exchange (separate customer/manager identities)")


if __name__ == "__main__":
    main()

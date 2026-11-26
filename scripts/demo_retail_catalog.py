"""browser/API smoke check; requires the existing FastAPI server running.

Uses synthetic-only demo credentials. Does not call Groq or create transactions.
"""
import os
import httpx

base = os.getenv("RETAILAI_API_URL", "http://127.0.0.1:8000").rstrip("/")
roles = {
    "customer": {"X-Demo-Token": "demo-northstar-customer-c3"},
    "staff": {"X-Demo-Token": "demo-northstar-agent"},
}


def main():
    with httpx.Client(base_url=base, timeout=10.0) as client:
        all_catalog = client.get("/customer/catalog", headers=roles["customer"])
        all_catalog.raise_for_status()
        products = all_catalog.json()
        print("SYNTHETIC SHARED CATALOG")
        print("Customer products:", len(products))
        print("Categories:", ", ".join(sorted({p["category"] for p in products})))
        query = {"q": "heels", "color": "black", "size": "US 8",
                 "max_price_cents": 7000, "in_stock": "true"}
        for role, endpoint in (("customer", "/customer/catalog"), ("staff", "/catalog")):
            resp = client.get(endpoint, headers=roles[role], params=query)
            resp.raise_for_status()
            matches = resp.json()
            print(f"{role.title()} filtered result:", [p["title"] for p in matches])
            assert len(matches) == 1 and matches[0]["id"] == "N-P-HEELS"
            assert len(matches[0]["variants"]) == 1
            assert matches[0]["variants"][0]["available_quantity"] == 6
        original_order = client.get("/customer/orders", headers=roles["customer"])
        original_order.raise_for_status()
        assert any(order["id"] == "N-1003" for order in original_order.json())
        print("Existing leggings order N-1003: preserved")
        print("PASS — customer/staff catalog, filters, stock, existing order")


if __name__ == "__main__":
    main()

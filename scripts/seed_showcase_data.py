"""Optional, idempotent synthetic records for the seven-day operations dashboard.

Run from RetailAI repo ROOT: python scripts/seed_showcase_data.py --apply
Stop the backend first. Only SQLite is supported; your DB gets a timestamped backup.
No actual checkout, inventory, payments or external service calls occur.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, make_engine, make_session_factory
from app.models import (CheckoutReceipt, Customer, Message, Order, OrderLine,
                        ProductVariant, Tenant, Ticket)
from app.seed import seed_demo
from app.retail_catalog import seed_retail_catalog

DAILY_TICKETS = (3, 2, 4, 3, 5, 4, 4)
DAILY_ORDERS = (2, 3, 3, 4, 2, 5, 3)
TICKET_TEMPLATES = (
    ("shipping", "Where is my fashion order?", "Could you check my package tracking?"),
    ("returns", "Request to return a purchase", "Please explain the return conditions."),
    ("exchanges", "Exchange to another size", "I'd like to check a different size."),
    ("general", "Help choosing a new outfit", "I need advice about a casual outfit."),
    ("shipping", "Delivery estimate inquiry", "What is the shipping window?"),
    ("returns", "Item return eligibility", "Is the item eligible for a return?"),
)
CUSTOMERS_AND_ORDERS = (("N-C1", "N-1001"), ("N-C2", "N-1002"), ("N-C5", "N-1005"))


def seed_showcase(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Add (never replace) clearly named synthetic dashboard fixtures."""
    now = now or datetime.now(timezone.utc)
    if db.get(Tenant, "northstar") is None:
        raise RuntimeError("Northstar seed data is missing; start the backend once first")
    for customer, order in CUSTOMERS_AND_ORDERS:
        if db.get(Customer, customer) is None or db.get(Order, order) is None:
            raise RuntimeError("Required demo customer/order fixtures are missing")
    variants = list(db.scalars(select(ProductVariant).where(
        ProductVariant.tenant_id == "northstar").order_by(ProductVariant.id)).all())
    if not variants:
        raise RuntimeError("Fashion product catalog is missing; start the backend once first")
    created_tickets = created_orders = 0
    ticket_index = order_index = 0
    for days_ago in range(6, -1, -1):
        day = now - timedelta(days=days_ago)
        for j in range(DAILY_TICKETS[6-days_ago]):
            ticket_index += 1
            ticket_id = f"SHOW-T-{ticket_index:03d}"
            if db.get(Ticket, ticket_id) is not None:
                continue
            cid, linked_order = CUSTOMERS_AND_ORDERS[ticket_index % len(CUSTOMERS_AND_ORDERS)]
            intent, subject, content = TICKET_TEMPLATES[ticket_index % len(TICKET_TEMPLATES)]
            created = day.replace(hour=9+(j*2)%11, minute=(j*13)%60)
            status = ("open", "in_progress", "resolved", "closed")[ticket_index % 4]
            db.add(Ticket(id=ticket_id, tenant_id="northstar", customer_id=cid,
                order_id=linked_order, subject=subject, content=content,
                intent=intent, status=status, created_at=created))
            db.add(Message(id=f"{ticket_id}-M1", tenant_id="northstar",
                ticket_id=ticket_id, sender="customer", body=content,
                delivery_status="received", created_at=created))
            created_tickets += 1
        for j in range(DAILY_ORDERS[6-days_ago]):
            order_index += 1
            order_id = f"RA-SHOW-{order_index:03d}"
            if db.get(Order, order_id) is not None:
                continue
            cid, _ = CUSTOMERS_AND_ORDERS[order_index % len(CUSTOMERS_AND_ORDERS)]
            variant = variants[order_index % len(variants)]
            created = day.replace(hour=10+(j*2)%10, minute=(j*7)%60)
            simulated = order_index % 3 == 0
            amount = variant.price_cents
            db.add(Order(id=order_id, tenant_id="northstar", customer_id=cid,
                fulfillment_status="payment_simulated_demo" if simulated else "awaiting_payment_demo",
                tracking_number=None, total_cents=amount, refundable_cents=0,
                currency="USD", placed_at=created, delivered_at=None))
            db.add(OrderLine(id=f"SHOW-L-{order_index:03d}", tenant_id="northstar",
                order_id=order_id, variant_id=variant.id, quantity=1, final_sale=False))
            db.add(CheckoutReceipt(id=f"SHOW-R-{order_index:03d}", tenant_id="northstar",
                customer_id=cid, idempotency_key=f"showcase-history-{order_index:03d}",
                quote_token=f"{order_index:064x}", order_id=order_id,
                total_cents=amount,
                items_snapshot=[{"variant_id": variant.id, "product_title": "Synthetic catalog item",
                                 "size": variant.size, "color": variant.color, "quantity": 1,
                                 "unit_price_cents": amount, "line_total_cents": amount}],
                status="sandbox_payment_simulated" if simulated else "sandbox_order_created",
                created_at=created))
            created_orders += 1
    db.commit()
    return {"tickets_added": created_tickets, "demo_orders_added": created_orders}


def _configured_url() -> str:
    # Mirrors run_backend.py's .env-file behavior without printing any secrets.
    if "DATABASE_URL" in os.environ:
        return os.environ["DATABASE_URL"]
    dotenv = REPO_ROOT / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"\'')
    return "sqlite:///./sportswear_demo.db"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Back up SQLite and add synthetic showcase records")
    args = parser.parse_args()
    if not args.apply:
        print("DRY RUN: No changes. Run with --apply to add seven days of synthetic metrics.")
        return
    os.chdir(REPO_ROOT)
    url = _configured_url()
    if not url.startswith("sqlite:///") or url == "sqlite:///:memory:":
        raise SystemExit("This optional showcase seeder supports only the local SQLite database")
    db_path = Path(url[len("sqlite:///"):]).resolve()
    if not db_path.is_file():
        raise SystemExit(f"Local database missing: {db_path}. Start FastAPI once to initialize it.")
    backup = db_path.with_name(db_path.name + f".before-showcase-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak")
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    engine = make_engine(url)
    try:
        with make_session_factory(engine)() as db:
            counts = seed_showcase(db)
    finally:
        engine.dispose()
    print(f"RetailAI showcase seed: PASS | {counts['tickets_added']} tickets + {counts['demo_orders_added']} orders added")
    print("Records are synthetic, dated over the last seven days, and safe to rerun (idempotent IDs).")
    print(f"SQLite backup: {backup}")
    print("No inventory decremented, card charges, external APIs or Groq calls.")

if __name__ == "__main__":
    main()

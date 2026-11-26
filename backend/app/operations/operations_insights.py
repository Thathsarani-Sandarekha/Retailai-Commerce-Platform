"""Read-only, tenant-scoped operations reporting for the local RetailAI sandbox.

Every metric is computed from persisted application records; this service does not
call an LLM, alter tickets or inventory, or infer real sales/payment outcomes.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..customers.auth import Actor, authenticate_staff
from ..models import (AuditEvent, CheckoutReceipt, ExchangeRecord,
                     ExchangeRequest, Product, ProductVariant, Ticket)

_PENDING_EXCHANGE = {
    "pending_customer_confirmation", "pending_staff_review",
    "pending_approval", "approved_not_executed",
}
_OPEN_TICKETS = {
    "open", "pending", "awaiting_staff_review", "awaiting_manager_approval",
    "escalated", "exchange_processing", "in_progress",
}
_RESOLVED_TICKETS = {"resolved", "closed"}


def _utc(value: datetime) -> datetime:
    """SQLite may return naive datetimes for UTC timestamps."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def calculate_insights(db: Session, actor: Actor) -> dict:
    t = actor.tenant_id
    now = datetime.now(timezone.utc)
    tickets = list(db.scalars(select(Ticket).where(Ticket.tenant_id == t)).all())
    checkouts = list(db.scalars(select(CheckoutReceipt).where(CheckoutReceipt.tenant_id == t)
                               .order_by(CheckoutReceipt.created_at.desc())).all())
    proposals = list(db.scalars(select(ExchangeRequest).where(ExchangeRequest.tenant_id == t)).all())
    exchanges = list(db.scalars(select(ExchangeRecord).where(ExchangeRecord.tenant_id == t)).all())
    products = {p.id: p for p in db.scalars(select(Product).where(Product.tenant_id == t)).all()}
    variants = list(db.scalars(select(ProductVariant).where(ProductVariant.tenant_id == t)).all())
    audits = list(db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == t)
                             .order_by(AuditEvent.created_at.desc())).all())

    ticket_statuses = Counter(tk.status for tk in tickets)
    ticket_intents = Counter(tk.intent for tk in tickets)
    pending_count = sum(p.status in _PENDING_EXCHANGE for p in proposals)
    reserved_count = sum(x.status == "reserved_awaiting_return" for x in exchanges)
    low_count = sum(0 < v.available_quantity <= 5 for v in variants)
    out_count = sum(v.available_quantity == 0 for v in variants)
    agent_replies = sum(a.event in {"agent_draft_created", "customer_agent_replied"} for a in audits)
    tool_events = [a for a in audits if a.event in {"agent_tool_invoked", "customer_agent_tool_invoked"}]
    failed_tool_count = sum(a.details.get("status") != "ok" for a in tool_events)

    activity = {}
    for days_ago in range(6, -1, -1):
        key = (now - timedelta(days=days_ago)).date().isoformat()
        activity[key] = {"date": key, "tickets": 0, "demo_orders": 0}
    for ticket in tickets:
        day = _utc(ticket.created_at).date().isoformat()
        if day in activity:
            activity[day]["tickets"] += 1
    for receipt in checkouts:
        day = _utc(receipt.created_at).date().isoformat()
        if day in activity:
            activity[day]["demo_orders"] += 1

    tool_summary = defaultdict(lambda: {"calls": 0, "ok": 0, "failed": 0})
    for event in tool_events:
        # Only names and statuses are returned, not tool arguments or chat content.
        name = str(event.details.get("tool", "unknown"))[:50]
        group = tool_summary[name]
        group["calls"] += 1
        group["ok" if event.details.get("status") == "ok" else "failed"] += 1

    inventory = [{
        "product_id": v.product_id,
        "product_title": products[v.product_id].title if v.product_id in products else "Unknown product",
        "category": products[v.product_id].category if v.product_id in products else "unknown",
        "variant_id": v.id,
        "sku": v.sku,
        "size": v.size, "color": v.color,
        "price_cents": v.price_cents,
        "available_quantity": v.available_quantity,
        "level": "out" if v.available_quantity == 0 else "low" if v.available_quantity <= 5 else "healthy",
    } for v in variants]
    inventory.sort(key=lambda row: (row["available_quantity"], row["product_title"], row["size"]))

    return {
        "generated_at": now.isoformat(),
        "environment": "synthetic_local_demo",
        "currency": "USD",
        "metrics": {
            "total_tickets": len(tickets),
            "open_tickets": sum(tk.status in _OPEN_TICKETS for tk in tickets),
            "resolved_tickets": sum(tk.status in _RESOLVED_TICKETS for tk in tickets),
            "escalated_tickets": ticket_statuses.get("escalated", 0),
            "pending_exchanges": pending_count,
            "reserved_exchanges": reserved_count,
            "sandbox_orders": len(checkouts),
            "demo_payments_simulated": sum(r.status == "sandbox_payment_simulated" for r in checkouts),
            "sandbox_order_value_cents": sum(r.total_cents for r in checkouts),
            "low_stock_variants": low_count,
            "out_of_stock_variants": out_count,
            "catalog_products": len(products),
            "ai_responses": agent_replies,
            "tool_calls": len(tool_events),
            "tool_failures": failed_tool_count,
        },
        "payment_note": "Synthetic order value is not revenue. Demo payments do not charge cards or money.",
        "ticket_statuses": dict(sorted(ticket_statuses.items())),
        "ticket_intents": dict(sorted(ticket_intents.items())),
        "daily_activity": list(activity.values()),
        "inventory": inventory,
        "recent_orders": [{
            "reference": r.id, "order_id": r.order_id, "customer_id": r.customer_id,
            "total_cents": r.total_cents, "status": r.status,
            "payment_status": "simulated_paid" if r.status == "sandbox_payment_simulated" else "not_charged", "created_at": _utc(r.created_at).isoformat(),
            "item_count": sum(int(item.get("quantity", 0)) for item in r.items_snapshot),
        } for r in checkouts[:50]],
        "recent_tickets": [{
            "id": tk.id, "subject": tk.subject, "status": tk.status,
            "intent": tk.intent, "order_id": tk.order_id,
            "created_at": _utc(tk.created_at).isoformat(),
        } for tk in sorted(tickets, key=lambda x: _utc(x.created_at), reverse=True)[:30]],
        "tool_summary": [{"tool": name, **counts} for name, counts in
                         sorted(tool_summary.items(), key=lambda entry: (-entry[1]["calls"], entry[0]))],
        "recent_audit": [{
            "event": a.event, "actor_id": a.actor_id,
            "resource_id": a.resource_id,
            "created_at": _utc(a.created_at).isoformat(),
        } for a in audits[:30]],
        "notes": [
            "Ticket status, intent and activity are computed from stored synthetic tickets.",
            "AI counts are observed audit events, not autonomous-resolution or quality scores.",
            "No customer-satisfaction, response-time, conversion, or paid-revenue claims are calculated.",
        ],
    }


def mount_operations_insights(app, db_session):
    router = APIRouter(prefix="/operations", tags=["Business analytics — local sandbox"])

    @router.get("/insights")
    def insights(actor: Actor = Depends(authenticate_staff),
                 db: Session = Depends(db_session)):
        return calculate_insights(db, actor)

    app.include_router(router)

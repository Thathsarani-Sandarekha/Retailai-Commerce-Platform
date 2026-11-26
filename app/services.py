import re
import uuid
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import Actor
from .models import AuditEvent, Order, Policy, Ticket


RULES = (
    # Explicit exchanges take priority over generic mentions of a return/refund.
    ("exchanges", (r"\bexchange\b", r"\bswap\b", r"different size", r"wrong size", r"too small", r"too big", r"size up", r"size down")),
    ("missing_package", (r"missing package", r"parcel missing", r"never arrived", r"not arrived", r"delivery exception", r"lost package")),
    ("refunds", (r"\brefund\b", r"money back", r"charged twice", r"reimburse")),
    ("returns", (r"\breturn\b", r"send it back", r"wore at the gym")),
    ("order_tracking", (r"\btrack", r"where is my order", r"delivery status", r"tracking number")),
    ("shipping", (r"\bshipping\b", r"ship to", r"delivery fee", r"shipping cost", r"how long.*deliver")),
    ("policy_question", (r"\bpolicy\b", r"terms and conditions", r"warranty")),
)

def classify(text: str) -> str:
    """Transparent rule-based baseline; deliberately not an AI classifier."""
    text = text.lower()
    for intent, patterns in RULES:
        if any(re.search(pattern, text) for pattern in patterns):
            return intent
    return "other"


def get_ticket(db: Session, actor: Actor, ticket_id: str) -> Ticket:
    ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == actor.tenant_id))
    if ticket is None or (actor.role == "customer" and ticket.customer_id != actor.customer_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


def get_authorized_order(db: Session, actor: Actor, ticket: Ticket) -> Order | None:
    if not ticket.order_id:
        return None
    order = db.scalar(select(Order).where(
        Order.id == ticket.order_id,
        Order.tenant_id == actor.tenant_id,
        Order.customer_id == ticket.customer_id,
    ))
    if order is None:
        # No fallback to unscoped ID lookup. Do not leak whether an order exists.
        raise HTTPException(status_code=404, detail="Associated order not found")
    return order


def matching_policies(db: Session, actor: Actor, intent: str) -> list[Policy]:
    category = {
        "order_tracking": "shipping", "shipping": "shipping",
        "returns": "returns", "refunds": "returns", "exchanges": "exchanges",
        "missing_package": "shipping", "policy_question": "general",
    }.get(intent)
    if category is None:
        return []
    return list(db.scalars(select(Policy).where(
        Policy.tenant_id == actor.tenant_id, Policy.category == category,
    ).order_by(Policy.id)).all())


def audit(db: Session, actor: Actor, event: str, resource_id: str, **allowed_details):
    # Caller must supply only controlled identifiers and enums, never raw messages/PII.
    db.add(AuditEvent(id=str(uuid.uuid4()), tenant_id=actor.tenant_id,
                      actor_id=actor.id, event=event,
                      resource_id=resource_id, details=allowed_details))

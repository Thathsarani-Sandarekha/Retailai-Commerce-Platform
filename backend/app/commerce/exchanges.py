"""Deterministic size-exchange checks; AI/customer text is never an authority."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..customers.auth import Actor
from ..models import OrderLine, Product, ProductVariant, Ticket
from ..schemas import ExchangeCheckRequest, ExchangeCheckView
from ..services import get_authorized_order

WINDOW_DAYS = 30  # Matches the fictional N-EXCHANGES demo-v2 policy fixture.
POLICY_REF = "N-EXCHANGES@demo-v2"


def exchange_check(db: Session, actor: Actor, ticket: Ticket, request: ExchangeCheckRequest) -> ExchangeCheckView:
    if actor.tenant_id != "northstar":
        raise HTTPException(422, "Size-exchange demo rules are configured for Northstar Athletics only")
    order = get_authorized_order(db, actor, ticket)
    if order is None:
        raise HTTPException(422, "Ticket has no authorized order")
    line = db.scalar(select(OrderLine).where(OrderLine.id == request.order_line_id,
        OrderLine.tenant_id == actor.tenant_id, OrderLine.order_id == order.id))
    if line is None:
        raise HTTPException(404, "Order line not found")
    current = db.scalar(select(ProductVariant).where(ProductVariant.id == line.variant_id,
        ProductVariant.tenant_id == actor.tenant_id))
    target = db.scalar(select(ProductVariant).where(ProductVariant.id == request.target_variant_id,
        ProductVariant.tenant_id == actor.tenant_id))
    if current is None or target is None:
        raise HTTPException(404, "Product variant not found")
    product = db.scalar(select(Product).where(Product.id == current.product_id,
        Product.tenant_id == actor.tenant_id))
    if product is None:
        raise HTTPException(404, "Product not found")
    delivery = order.delivered_at
    if delivery and delivery.tzinfo is None:
        delivery = delivery.replace(tzinfo=timezone.utc)  # SQLite removes timezone annotations.
    age_days = (datetime.now(timezone.utc) - delivery).total_seconds() / 86400 if delivery else None
    checks = {
        "order_delivered": delivery is not None and order.fulfillment_status == "delivered",
        "within_30_day_window": age_days is not None and 0 <= age_days <= WINDOW_DAYS,
        "not_final_sale": not line.final_sale and product.exchangeable,
        "same_product": current.product_id == target.product_id,
        "different_variant": current.id != target.id,
        "same_color": current.color == target.color,
        "stock_available": target.available_quantity >= line.quantity,
        "staff_condition_attested": request.item_condition == "unworn_with_tags",
    }
    names = {
        "order_delivered": "Confirmed delivery is required",
        "within_30_day_window": "Outside 30 calendar days after delivery or not delivered",
        "not_final_sale": "Final-sale or non-exchangeable item",
        "same_product": "Target variant belongs to a different product",
        "different_variant": "Target variant must differ from original",
        "same_color": "Size exchanges cannot silently change the product color",
        "stock_available": "Requested variant has insufficient available stock",
        "staff_condition_attested": "Staff must verify unworn/unwashed condition with tags",
    }
    return ExchangeCheckView(ticket_id=ticket.id, order_id=order.id, order_line_id=line.id,
                             target_variant_id=target.id, eligible_for_proposal=all(checks.values()),
                             checks=checks, reasons=[names[key] for key, good in checks.items() if not good],
                             evidence_policy=POLICY_REF)

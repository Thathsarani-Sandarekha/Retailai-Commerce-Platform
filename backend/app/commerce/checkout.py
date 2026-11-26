"""Local synthetic checkout: re-price, atomically decrement stock and create an unpaid order.

This is NOT a payment or Shopify checkout. Every mutation is explicitly customer
confirmed; model tools are read-only. Database constraints and conditional stock
updates protect the order operation from duplicate retries and overselling.
"""
import hashlib
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..customers.auth import Actor, authenticate, require_role
from .cart import view as cart_view
from ..models import CartItem, CheckoutReceipt, Order, OrderLine, ProductVariant, utcnow
from ..services import audit


class ConfirmCheckout(BaseModel):
    confirmed: bool
    quote_token: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


def quote(db: Session, actor: Actor) -> dict:
    if actor.role != "customer" or not actor.customer_id:
        raise HTTPException(403, "Customer identity required")
    cart = cart_view(db, actor)
    if not cart["items"]:
        raise HTTPException(409, "Cart is empty")
    if not cart["stock_ok"]:
        raise HTTPException(409, "Cart stock changed; update your cart before checkout")
    # Server-derived fingerprint binds the quote to the exact customer/cart/price state.
    # It is a stale-quote detector, NOT an authentication mechanism or payment token.
    document = {
        "tenant_id": actor.tenant_id, "customer_id": actor.customer_id,
        "currency": cart["currency"], "subtotal_cents": cart["subtotal_cents"],
        "items": sorted([{"variant_id": item["variant_id"],
                          "quantity": item["quantity"],
                          "unit_price_cents": item["unit_price_cents"]}
                         for item in cart["items"]], key=lambda item: item["variant_id"]),
    }
    fingerprint = hashlib.sha256(json.dumps(document, sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest()
    return {"quote_token": fingerprint, "currency": "USD", "items": cart["items"],
            "item_count": cart["item_count"], "subtotal_cents": cart["subtotal_cents"],
            "tax_cents": 0, "shipping_cents": 0,
            "total_cents": cart["subtotal_cents"],
            "payment_status": "not_charged", "stock_reserved": False,
            "notice": "Synthetic checkout preview. Tax and shipping are not modeled. No payment will be taken."}


def receipt_view(r: CheckoutReceipt, repeated: bool = False) -> dict:
    paid = r.status == "sandbox_payment_simulated"
    return {"reference": r.id, "order_id": r.order_id, "status": r.status,
            "payment_status": "simulated_paid" if paid else "not_charged", "currency": "USD", "total_cents": r.total_cents,
            "items": r.items_snapshot, "created_at": r.created_at.isoformat(),
            "duplicate_request": repeated,
            "notice": ("Demo payment recorded; no card or money was charged." if paid
                       else "Synthetic local order only. No charge, Shopify order or shipment created.")}


class SimulatePayment(BaseModel):
    # Must be a separate, explicit customer action. Never store or collect card data.
    confirmed: bool


def mount_checkout_routes(app, db_session):
    router = APIRouter(prefix="/customer/checkout", tags=["Sandbox checkout — customer"])

    def customer(actor: Actor = Depends(authenticate)) -> Actor:
        require_role(actor, "customer")
        return actor

    @router.get("/preview")
    def preview(actor: Actor = Depends(customer), db: Session = Depends(db_session)):
        return quote(db, actor)

    @router.post("/confirm", status_code=201)
    def confirm(payload: ConfirmCheckout, actor: Actor = Depends(customer),
                db: Session = Depends(db_session)):
        if not payload.confirmed:
            raise HTTPException(422, "Explicit customer confirmation required")
        key_filter = (CheckoutReceipt.tenant_id == actor.tenant_id,
                      CheckoutReceipt.customer_id == actor.customer_id,
                      CheckoutReceipt.idempotency_key == payload.idempotency_key)
        previous = db.scalar(select(CheckoutReceipt).where(*key_filter))
        if previous is not None:
            if previous.quote_token != payload.quote_token:
                raise HTTPException(409, "Idempotency key used for a different checkout")
            return receipt_view(previous, repeated=True)

        # Lock existing cart rows (PostgreSQL) before validating; SQLite ignores FOR UPDATE
        # but its write serialization plus conditional variant updates protect stock counts.
        db.scalars(select(CartItem).where(
            CartItem.tenant_id == actor.tenant_id,
            CartItem.customer_id == actor.customer_id).with_for_update()).all()
        current = quote(db, actor)  # Checks exact live prices, quantities and stock.
        if current["quote_token"] != payload.quote_token:
            raise HTTPException(409, "Cart or pricing changed; review a new checkout preview")

        order_id = "RA-" + uuid4().hex[:12].upper()
        receipt_id = "RC-" + uuid4().hex[:12].upper()
        snapshot = []
        for item in current["items"]:
            changed = db.execute(update(ProductVariant).where(
                ProductVariant.tenant_id == actor.tenant_id,
                ProductVariant.id == item["variant_id"],
                ProductVariant.available_quantity >= item["quantity"],
                # Enforce the price displayed in the confirmed quote.
                ProductVariant.price_cents == item["unit_price_cents"],
            ).values(available_quantity=ProductVariant.available_quantity-item["quantity"])
                .execution_options(synchronize_session=False))
            if changed.rowcount != 1:
                db.rollback()
                raise HTTPException(409, "Stock or price changed; review your cart and try again")
            snapshot.append({"variant_id": item["variant_id"],
                "product_title": item["product_title"], "size": item["size"],
                "color": item["color"], "quantity": item["quantity"],
                "unit_price_cents": item["unit_price_cents"],
                "line_total_cents": item["line_total_cents"]})

        order = Order(id=order_id, tenant_id=actor.tenant_id,
            customer_id=actor.customer_id, fulfillment_status="awaiting_payment_demo",
            tracking_number=None, total_cents=current["total_cents"],
            refundable_cents=0, currency="USD", placed_at=utcnow(), delivered_at=None)
        db.add(order)
        for item in snapshot:
            db.add(OrderLine(id=str(uuid4()), tenant_id=actor.tenant_id,
                order_id=order_id, variant_id=item["variant_id"],
                quantity=item["quantity"], final_sale=False))
        r = CheckoutReceipt(id=receipt_id, tenant_id=actor.tenant_id,
            customer_id=actor.customer_id, idempotency_key=payload.idempotency_key,
            quote_token=payload.quote_token, order_id=order_id,
            total_cents=current["total_cents"], items_snapshot=snapshot,
            status="sandbox_order_created")
        db.add(r)
        db.execute(delete(CartItem).where(
            CartItem.tenant_id == actor.tenant_id,
            CartItem.customer_id == actor.customer_id))
        audit(db, actor, "sandbox_checkout_confirmed", order_id,
              item_count=current["item_count"], total_cents=current["total_cents"])
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            previous = db.scalar(select(CheckoutReceipt).where(*key_filter))
            if previous is not None and previous.quote_token == payload.quote_token:
                return receipt_view(previous, repeated=True)
            raise HTTPException(409, "Checkout conflicted; refresh and try again") from None
        return receipt_view(r)

    @router.post("/orders/{order_id}/simulate-payment")
    def simulate_payment(order_id: str, payload: SimulatePayment,
                         actor: Actor = Depends(customer),
                         db: Session = Depends(db_session)):
        """Idempotent no-charge payment step for the local synthetic demo only."""
        if not payload.confirmed:
            raise HTTPException(422, "Customer must explicitly confirm the demo payment")
        receipt = db.scalar(select(CheckoutReceipt).where(
            CheckoutReceipt.tenant_id == actor.tenant_id,
            CheckoutReceipt.customer_id == actor.customer_id,
            CheckoutReceipt.order_id == order_id))
        if receipt is None:
            raise HTTPException(404, "Demo checkout not found")
        if receipt.status == "sandbox_payment_simulated":
            return receipt_view(receipt, repeated=True)
        if receipt.status != "sandbox_order_created":
            raise HTTPException(409, "Demo order is not eligible for payment simulation")
        # Only the demo flag is changed; no payment APIs, stock mutation or shipments.
        receipt.status = "sandbox_payment_simulated"
        order = db.scalar(select(Order).where(
            Order.id == order_id, Order.tenant_id == actor.tenant_id,
            Order.customer_id == actor.customer_id))
        if order is None:
            db.rollback()
            raise HTTPException(409, "Order record missing")
        order.fulfillment_status = "payment_simulated_demo"
        audit(db, actor, "sandbox_payment_simulated", order_id)
        db.commit()
        db.refresh(receipt)
        return receipt_view(receipt)

    @router.get("/orders")
    def orders(actor: Actor = Depends(customer), db: Session = Depends(db_session)):
        rows = db.scalars(select(CheckoutReceipt).where(
            CheckoutReceipt.tenant_id == actor.tenant_id,
            CheckoutReceipt.customer_id == actor.customer_id,
        ).order_by(CheckoutReceipt.created_at.desc())).all()
        return [receipt_view(r) for r in rows]

    app.include_router(router)

    # Staff operations read the same committed checkout receipts through the
    # business service; no LLM call, no mutation and tenant-scoped access.
    operations = APIRouter(prefix="/operations", tags=["Store operations — local demo"])

    @operations.get("/sandbox-orders")
    def staff_orders(actor: Actor = Depends(authenticate),
                     db: Session = Depends(db_session)):
        if actor.role not in ("agent", "manager"):
            raise HTTPException(403, "Staff access required")
        rows = db.scalars(select(CheckoutReceipt).where(
            CheckoutReceipt.tenant_id == actor.tenant_id,
        ).order_by(CheckoutReceipt.created_at.desc()).limit(100)).all()
        return [{**receipt_view(r), "customer_id": r.customer_id} for r in rows]

    app.include_router(operations)

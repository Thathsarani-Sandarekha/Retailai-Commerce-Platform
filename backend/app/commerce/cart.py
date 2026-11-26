"""Transactional synthetic customer cart.

Cart operations never change inventory or create orders. All totals and variant
permissions are computed by the server, scoped to the authenticated demo actor.
Replace the demo identity layer with real sessions before any public deployment.
"""
import hashlib
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..customers.auth import Actor, authenticate, require_role
from ..models import CartItem, CartMutation, Product, ProductVariant
from ..services import audit

MAX_CART_QTY = 20


class AddCartItem(BaseModel):
    variant_id: str = Field(min_length=1, max_length=60)
    quantity: int = Field(ge=1, le=MAX_CART_QTY)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class SetCartQuantity(BaseModel):
    quantity: int = Field(ge=1, le=MAX_CART_QTY)


def view(db: Session, actor: Actor) -> dict:
    rows = db.scalars(select(CartItem).where(
        CartItem.tenant_id == actor.tenant_id,
        CartItem.customer_id == actor.customer_id,
    ).order_by(CartItem.created_at, CartItem.id)).all()
    items = []
    for row in rows:
        variant = db.scalar(select(ProductVariant).where(
            ProductVariant.id == row.variant_id,
            ProductVariant.tenant_id == actor.tenant_id))
        product = (db.scalar(select(Product).where(
            Product.id == variant.product_id, Product.tenant_id == actor.tenant_id))
            if variant is not None else None)
        if variant is None or product is None:
            # Fail closed rather than leaking or guessing a price for stale references.
            raise HTTPException(409, "Cart references an unavailable catalog item")
        items.append({
            "variant_id": variant.id, "product_id": product.id,
            "product_title": product.title, "category": product.category,
            "size": variant.size, "color": variant.color,
            "quantity": row.quantity, "unit_price_cents": variant.price_cents,
            "line_total_cents": row.quantity * variant.price_cents,
            "available_quantity": variant.available_quantity,
            "stock_ok": row.quantity <= variant.available_quantity,
        })
    return {
        "customer_id": actor.customer_id,
        "currency": "USD",  # Explicit US demo catalog currency.
        "items": items,
        "item_count": sum(item["quantity"] for item in items),
        "subtotal_cents": sum(item["line_total_cents"] for item in items),
        "stock_ok": all(item["stock_ok"] for item in items),
        "checkout_enabled": bool(items) and all(item["stock_ok"] for item in items),
        "notice": "Local synthetic cart. Checkout requires explicit confirmation; no payment is taken.",
    }


def mount_cart_routes(app, db_session):
    router = APIRouter(prefix="/customer/cart", tags=["Customer cart — local demo"])

    def customer(actor: Actor = Depends(authenticate)) -> Actor:
        require_role(actor, "customer")
        return actor

    def valid_variant(db: Session, actor: Actor, variant_id: str) -> ProductVariant:
        variant = db.scalar(select(ProductVariant).where(
            ProductVariant.id == variant_id,
            ProductVariant.tenant_id == actor.tenant_id))
        if variant is None:
            raise HTTPException(404, "Product variant not found")
        return variant

    @router.get("")
    def get_cart(actor: Actor = Depends(customer), db: Session = Depends(db_session)):
        return view(db, actor)

    @router.post("/items", status_code=200)
    def add_item(payload: AddCartItem, actor: Actor = Depends(customer),
                 db: Session = Depends(db_session)):
        canonical = json.dumps({"variant_id": payload.variant_id,
                                "quantity": payload.quantity}, sort_keys=True)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        key_filter = (CartMutation.tenant_id == actor.tenant_id,
                      CartMutation.customer_id == actor.customer_id,
                      CartMutation.idempotency_key == payload.idempotency_key)
        previous = db.scalar(select(CartMutation).where(*key_filter))
        if previous is not None:
            if previous.payload_hash != digest:
                raise HTTPException(409, "Idempotency key was reused for different cart contents")
            return view(db, actor)
        variant = valid_variant(db, actor, payload.variant_id)
        row = db.scalar(select(CartItem).where(
            CartItem.tenant_id == actor.tenant_id,
            CartItem.customer_id == actor.customer_id,
            CartItem.variant_id == variant.id))
        next_qty = (row.quantity if row else 0) + payload.quantity
        if next_qty > MAX_CART_QTY or next_qty > variant.available_quantity:
            raise HTTPException(409, "Requested quantity exceeds the available cart limit or stock")
        if row is None:
            db.add(CartItem(id=str(uuid4()), tenant_id=actor.tenant_id,
                            customer_id=actor.customer_id, variant_id=variant.id,
                            quantity=next_qty))
        else:
            # SQL increment to avoid lost updates from independent cart additions.
            incremented = db.execute(update(CartItem).where(CartItem.id == row.id,
                CartItem.tenant_id == actor.tenant_id,
                CartItem.customer_id == actor.customer_id,
                CartItem.quantity <= MAX_CART_QTY-payload.quantity,
                CartItem.quantity <= variant.available_quantity-payload.quantity)
                .values(quantity=CartItem.quantity + payload.quantity)
                .execution_options(synchronize_session=False))
            if incremented.rowcount != 1:
                db.rollback()
                raise HTTPException(409, "Cart quantity changed; refresh before adding again")
        db.add(CartMutation(id=str(uuid4()), tenant_id=actor.tenant_id,
            customer_id=actor.customer_id, idempotency_key=payload.idempotency_key,
            payload_hash=digest))
        audit(db, actor, "cart_item_added", variant.id, quantity=payload.quantity)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            previous = db.scalar(select(CartMutation).where(*key_filter))
            if previous is not None and previous.payload_hash == digest:
                return view(db, actor)
            raise HTTPException(409, "Cart update conflicted; refresh and try again") from None
        return view(db, actor)

    @router.patch("/items/{variant_id}")
    def set_quantity(variant_id: str, payload: SetCartQuantity,
                     actor: Actor = Depends(customer), db: Session = Depends(db_session)):
        variant = valid_variant(db, actor, variant_id)
        if payload.quantity > variant.available_quantity:
            raise HTTPException(409, "Requested quantity is not available")
        updated = db.execute(update(CartItem).where(
            CartItem.tenant_id == actor.tenant_id,
            CartItem.customer_id == actor.customer_id,
            CartItem.variant_id == variant.id).values(quantity=payload.quantity)
            .execution_options(synchronize_session=False))
        if updated.rowcount != 1:
            db.rollback()
            raise HTTPException(404, "Cart item not found")
        audit(db, actor, "cart_quantity_set", variant.id, quantity=payload.quantity)
        db.commit()
        return view(db, actor)

    @router.delete("/items/{variant_id}")
    def remove_item(variant_id: str, actor: Actor = Depends(customer),
                    db: Session = Depends(db_session)):
        removed = db.execute(delete(CartItem).where(
            CartItem.tenant_id == actor.tenant_id,
            CartItem.customer_id == actor.customer_id,
            CartItem.variant_id == variant_id))
        if removed.rowcount:
            audit(db, actor, "cart_item_removed", variant_id)
        db.commit()
        return view(db, actor)

    app.include_router(router)

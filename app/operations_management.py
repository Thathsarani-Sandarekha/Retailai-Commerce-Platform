"""Small, deterministic management APIs for the SYNTHETIC local retail sandbox.

No LLM execution, Shopify mutation, or payment processing occurs here.
Staff may manage ticket triage. Only managers may change product data/stock.
"""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import Actor, authenticate_staff, require_role
from .models import ExchangeRequest, Product, ProductVariant, Ticket, TicketWorkItem, AuditEvent
from .services import audit

PRIORITIES = ("low", "normal", "high", "urgent")
TICKET_STATES = {
    "open": {"in_progress", "escalated", "resolved"},
    "in_progress": {"open", "escalated", "resolved"},
    "escalated": {"in_progress", "resolved"},
    "resolved": {"open"},
    "closed": {"open"},
}
PENDING_EXCHANGES = {"pending_customer_confirmation", "pending_staff_review",
                     "pending_approval", "approved_not_executed", "inventory_reserved"}


class VariantEdit(BaseModel):
    expected_available_quantity: int = Field(ge=0)
    new_available_quantity: int = Field(ge=0, le=1_000_000)
    expected_price_cents: int = Field(ge=0)
    new_price_cents: int = Field(ge=1, le=10_000_000)
    reason: str = Field(min_length=8, max_length=180)


class ProductEdit(BaseModel):
    expected_title: str = Field(min_length=2, max_length=140)
    expected_description: str = Field(min_length=1)
    expected_exchangeable: bool
    title: str = Field(min_length=2, max_length=140)
    description: str = Field(min_length=8, max_length=3000)
    exchangeable: bool
    reason: str = Field(min_length=8, max_length=180)


class TicketEdit(BaseModel):
    expected_status: str
    expected_version: int = Field(ge=0)
    status: Literal["open", "in_progress", "escalated", "resolved"]
    priority: Literal["low", "normal", "high", "urgent"]
    assigned_to: str | None = Field(default=None, max_length=60)


def inventory_view(db: Session, tenant_id: str) -> list[dict]:
    products = {p.id: p for p in db.scalars(select(Product).where(Product.tenant_id == tenant_id)).all()}
    rows = db.scalars(select(ProductVariant).where(ProductVariant.tenant_id == tenant_id).order_by(ProductVariant.sku)).all()
    return [{"variant_id": v.id, "product_id": v.product_id,
             "product_title": products[v.product_id].title, "description": products[v.product_id].description,
             "exchangeable": products[v.product_id].exchangeable,
             "category": products[v.product_id].category, "sku": v.sku,
             "size": v.size, "color": v.color, "price_cents": v.price_cents,
             "available_quantity": v.available_quantity} for v in rows]


def tickets_view(db: Session, tenant_id: str) -> list[dict]:
    notes = {n.id: n for n in db.scalars(select(TicketWorkItem).where(TicketWorkItem.tenant_id == tenant_id)).all()}
    tickets = db.scalars(select(Ticket).where(Ticket.tenant_id == tenant_id).order_by(Ticket.created_at.desc())).all()
    return [{"id": t.id, "subject": t.subject, "customer_id": t.customer_id,
             "order_id": t.order_id, "status": t.status, "intent": t.intent,
             "created_at": t.created_at,
             "priority": notes[t.id].priority if t.id in notes else "normal",
             "assigned_to": notes[t.id].assigned_to if t.id in notes else None,
             "version": notes[t.id].version if t.id in notes else 0} for t in tickets]


def mount_operations_management(app, db_session):
    router = APIRouter(prefix="/operations/manage", tags=["Retail management — synthetic local demo"])

    @router.get("/inventory")
    def list_inventory(actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        return inventory_view(db, actor.tenant_id)

    @router.patch("/variants/{variant_id}")
    def edit_variant(variant_id: str, payload: VariantEdit,
                     actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        require_role(actor, "manager")
        if (payload.new_available_quantity == payload.expected_available_quantity
                and payload.new_price_cents == payload.expected_price_cents):
            raise HTTPException(422, "No inventory or price change requested")
        # Compare-and-swap prevents lost updates when another checkout/reservation
        # or staff adjustment changed stock since the manager loaded the page.
        result = db.execute(update(ProductVariant).where(
            ProductVariant.id == variant_id,
            ProductVariant.tenant_id == actor.tenant_id,
            ProductVariant.available_quantity == payload.expected_available_quantity,
            ProductVariant.price_cents == payload.expected_price_cents,
        ).values(available_quantity=payload.new_available_quantity,
                 price_cents=payload.new_price_cents).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Variant not found or values changed; refresh before saving")
        audit(db, actor, "inventory_manager_adjusted", variant_id,
              before_quantity=payload.expected_available_quantity,
              after_quantity=payload.new_available_quantity,
              before_price_cents=payload.expected_price_cents,
              after_price_cents=payload.new_price_cents,
              reason_code="manager_manual_adjustment")
        db.commit()
        return next(row for row in inventory_view(db, actor.tenant_id) if row["variant_id"] == variant_id)

    @router.patch("/products/{product_id}")
    def edit_product(product_id: str, payload: ProductEdit,
                     actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        require_role(actor, "manager")
        result = db.execute(update(Product).where(
            Product.id == product_id, Product.tenant_id == actor.tenant_id,
            Product.title == payload.expected_title,
            Product.description == payload.expected_description,
            Product.exchangeable == payload.expected_exchangeable,
        ).values(title=payload.title.strip(), description=payload.description.strip(),
                 exchangeable=payload.exchangeable).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Product not found or title changed; refresh before saving")
        audit(db, actor, "product_manager_updated", product_id,
              reason_code="manager_catalog_edit")
        db.commit()
        product = db.scalar(select(Product).where(Product.id == product_id, Product.tenant_id == actor.tenant_id))
        return {"id": product.id, "title": product.title, "description": product.description,
                "category": product.category, "exchangeable": product.exchangeable}

    @router.get("/tickets")
    def list_work_items(actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        return tickets_view(db, actor.tenant_id)

    @router.patch("/tickets/{ticket_id}")
    def edit_ticket(ticket_id: str, payload: TicketEdit,
                    actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == actor.tenant_id))
        if ticket is None:
            raise HTTPException(404, "Ticket not found")
        meta = db.scalar(select(TicketWorkItem).where(
            TicketWorkItem.id == ticket_id, TicketWorkItem.tenant_id == actor.tenant_id))
        version = meta.version if meta else 0
        if payload.expected_status != ticket.status or payload.expected_version != version:
            raise HTTPException(409, "Ticket changed; refresh before saving")
        authorized_assignees = {f"{actor.tenant_id}-agent-1", f"{actor.tenant_id}-manager-1"}
        if payload.assigned_to is not None and payload.assigned_to not in authorized_assignees:
            raise HTTPException(422, "Assignee must be a known staff identity for this tenant")
        if payload.status != ticket.status and payload.status not in TICKET_STATES.get(ticket.status, set()):
            raise HTTPException(409, "Invalid ticket transition; exchange states use their own workflow")
        if payload.status == "resolved" and ticket.status != "resolved":
            pending = db.scalar(select(ExchangeRequest.id).where(
                ExchangeRequest.tenant_id == actor.tenant_id,
                ExchangeRequest.ticket_id == ticket_id,
                ExchangeRequest.status.in_(PENDING_EXCHANGES)).limit(1))
            if pending:
                raise HTTPException(409, "Pending exchange must complete or be rejected before resolving")
        if (payload.status == ticket.status and meta and payload.priority == meta.priority
                and payload.assigned_to == meta.assigned_to):
            return next(x for x in tickets_view(db, actor.tenant_id) if x["id"] == ticket_id)
        if payload.status != ticket.status:
            claimed = db.execute(update(Ticket).where(
                Ticket.id == ticket.id, Ticket.tenant_id == actor.tenant_id,
                Ticket.status == payload.expected_status).values(status=payload.status)
                .execution_options(synchronize_session=False))
            if claimed.rowcount != 1:
                db.rollback()
                raise HTTPException(409, "Ticket status changed; refresh before saving")
        if meta is None:
            meta = TicketWorkItem(id=ticket.id, tenant_id=actor.tenant_id, version=1,
                                  priority=payload.priority, assigned_to=payload.assigned_to,
                                  updated_at=datetime.now(timezone.utc))
            db.add(meta)
        else:
            changed = db.execute(update(TicketWorkItem).where(
                TicketWorkItem.id == ticket.id,
                TicketWorkItem.tenant_id == actor.tenant_id,
                TicketWorkItem.version == version,
            ).values(priority=payload.priority, assigned_to=payload.assigned_to,
                     updated_at=datetime.now(timezone.utc), version=version + 1)
            .execution_options(synchronize_session=False))
            if changed.rowcount != 1:
                db.rollback()
                raise HTTPException(409, "Ticket assignment changed; refresh before saving")
        audit(db, actor, "ticket_work_item_updated", ticket.id,
              old_status=payload.expected_status, new_status=payload.status,
              priority=payload.priority, assigned_to=payload.assigned_to or "unassigned")
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Ticket changed concurrently; refresh before saving")
        db.expire_all()
        return next(x for x in tickets_view(db, actor.tenant_id) if x["id"] == ticket_id)

    @router.get("/tickets/{ticket_id}/activity")
    def ticket_activity(ticket_id: str, actor: Actor = Depends(authenticate_staff),
                        db: Session = Depends(db_session)):
        ticket = db.scalar(select(Ticket.id).where(Ticket.id == ticket_id, Ticket.tenant_id == actor.tenant_id))
        if not ticket:
            raise HTTPException(404, "Ticket not found")
        events = db.scalars(select(AuditEvent).where(
            AuditEvent.tenant_id == actor.tenant_id,
            AuditEvent.resource_id == ticket_id).order_by(AuditEvent.created_at.desc()).limit(40)).all()
        return [{"event": e.event, "actor_id": e.actor_id,
                 "created_at": e.created_at} for e in events]

    app.include_router(router)

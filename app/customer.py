"""Customer self-service API mounted beside the existing internal support API.

All endpoints are restricted to a synthetic customer identity supplied by the
local credential mapping. This is NOT production authentication.
"""
import hashlib
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .agent import SingleAgent, TOOL_SCHEMAS
from .catalog import search_catalog
from .auth import Actor, authenticate, require_role
from .exchanges import POLICY_REF, exchange_check
from .models import (Customer, ExchangeConfirmation, ExchangeRecord, ExchangeRequest,
                     Message, Order, OrderLine, Policy, Product, ProductVariant,
                     Shipment, ShipmentEvent, Ticket)
from .schemas import (AgentChatRequest, ExchangeCheckRequest, ExchangeCheckView,
                      ExchangeActionView, MessageView, OrderLineView,
                      ProductCatalogView, ShipmentView, TicketCreate, TicketView)
from .services import audit, classify, get_ticket, matching_policies


class CustomerExchangeRequest(BaseModel):
    order_line_id: str = Field(min_length=1, max_length=60)
    target_variant_id: str = Field(min_length=1, max_length=60)
    confirmed: bool
    condition_attested: bool
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class VerifyConditionRequest(BaseModel):
    verified_unworn_with_tags: bool


def mount_customer_routes(app, db_session, support_agent: SingleAgent):
    router = APIRouter(tags=["Customer portal — local demo"])

    def customer_actor(actor: Actor = Depends(authenticate)) -> Actor:
        require_role(actor, "customer")
        return actor

    def own_ticket(db: Session, actor: Actor, ticket_id: str) -> Ticket:
        return get_ticket(db, actor, ticket_id)  # get_ticket enforces customer ownership.

    def own_order(db: Session, actor: Actor, order_id: str) -> Order:
        order = db.scalar(select(Order).where(Order.id == order_id,
                        Order.tenant_id == actor.tenant_id,
                        Order.customer_id == actor.customer_id))
        if order is None:
            raise HTTPException(404, "Order not found")
        return order

    def lines_for(db: Session, actor: Actor, order_id: str):
        lines = db.scalars(select(OrderLine).where(OrderLine.tenant_id == actor.tenant_id,
                           OrderLine.order_id == order_id).order_by(OrderLine.id)).all()
        result = []
        for line in lines:
            variant = db.scalar(select(ProductVariant).where(ProductVariant.id == line.variant_id,
                                   ProductVariant.tenant_id == actor.tenant_id))
            product = db.scalar(select(Product).where(Product.id == variant.product_id,
                                   Product.tenant_id == actor.tenant_id))
            result.append(OrderLineView(id=line.id, product_id=product.id,
                    product_title=product.title, variant_id=variant.id, size=variant.size,
                    color=variant.color, quantity=line.quantity, final_sale=line.final_sale))
        return result

    @router.get("/customer/profile")
    def profile(actor: Actor = Depends(customer_actor), db: Session = Depends(db_session)):
        person = db.scalar(select(Customer).where(Customer.id == actor.customer_id,
                           Customer.tenant_id == actor.tenant_id))
        if person is None:
            raise HTTPException(404, "Customer not found")
        return {"id": person.id, "display_name": person.display_name,
                "environment": "synthetic_local_demo"}

    @router.get("/customer/catalog", response_model=list[ProductCatalogView])
    def catalog(
        q: str | None = Query(default=None, max_length=80),
        category: str | None = Query(default=None, max_length=40),
        size: str | None = Query(default=None, max_length=20),
        color: str | None = Query(default=None, max_length=40),
        min_price_cents: int | None = Query(default=None, ge=0),
        max_price_cents: int | None = Query(default=None, ge=0),
        in_stock: bool = False,
        actor: Actor = Depends(customer_actor), db: Session = Depends(db_session),
    ):
        if (min_price_cents is not None and max_price_cents is not None
                and min_price_cents > max_price_cents):
            raise HTTPException(422, "min_price_cents cannot exceed max_price_cents")
        return search_catalog(db, actor.tenant_id, q=q, category=category,
            size=size, color=color, min_price_cents=min_price_cents,
            max_price_cents=max_price_cents, in_stock=in_stock)

    @router.get("/customer/orders")
    def orders(actor: Actor = Depends(customer_actor), db: Session = Depends(db_session)):
        rows = db.scalars(select(Order).where(Order.tenant_id == actor.tenant_id,
                    Order.customer_id == actor.customer_id).order_by(Order.placed_at.desc())).all()
        return [{"id": o.id, "status": o.fulfillment_status, "tracking_number": o.tracking_number,
                 "total_cents": o.total_cents, "currency": o.currency,
                 "delivered_at": o.delivered_at,
                 "items": [item.model_dump() for item in lines_for(db, actor, o.id)]}
                for o in rows]

    @router.get("/customer/tickets", response_model=list[TicketView])
    def tickets(actor: Actor = Depends(customer_actor), db: Session = Depends(db_session)):
        return db.scalars(select(Ticket).where(Ticket.tenant_id == actor.tenant_id,
                           Ticket.customer_id == actor.customer_id).order_by(Ticket.created_at.desc())).all()

    @router.post("/customer/tickets", response_model=TicketView, status_code=201)
    def create_ticket(payload: TicketCreate, actor: Actor = Depends(customer_actor),
                      db: Session = Depends(db_session)):
        if payload.customer_id != actor.customer_id:
            raise HTTPException(403, "Cannot create tickets for another customer")
        if payload.order_id:
            own_order(db, actor, payload.order_id)
        ticket = Ticket(id=str(uuid4()), tenant_id=actor.tenant_id,
            customer_id=actor.customer_id, order_id=payload.order_id, subject=payload.subject,
            content=payload.content, intent=classify(payload.subject+" "+payload.content), status="open")
        db.add(ticket)
        db.add(Message(id=str(uuid4()), tenant_id=actor.tenant_id,
            ticket_id=ticket.id, sender="customer", body=payload.content,
            delivery_status="received"))
        audit(db, actor, "customer_ticket_created", ticket.id)
        db.commit()
        db.refresh(ticket)
        return ticket

    @router.get("/customer/tickets/{ticket_id}/context")
    def context(ticket_id: str, actor: Actor = Depends(customer_actor), db: Session = Depends(db_session)):
        ticket = own_ticket(db, actor, ticket_id)
        order = own_order(db, actor, ticket.order_id) if ticket.order_id else None
        category = ticket.intent if ticket.intent != "unclassified" else classify(ticket.subject+" "+ticket.content)
        policies = matching_policies(db, actor, category)
        shipments = []
        if order is not None:
            for shipment in db.scalars(select(Shipment).where(Shipment.order_id == order.id,
                     Shipment.tenant_id == actor.tenant_id)).all():
                events = db.scalars(select(ShipmentEvent).where(
                     ShipmentEvent.shipment_id == shipment.id,
                     ShipmentEvent.tenant_id == actor.tenant_id).order_by(ShipmentEvent.event_at)).all()
                shipments.append(ShipmentView(id=shipment.id, carrier=shipment.carrier,
                    tracking_number=shipment.tracking_number, status=shipment.status,
                    estimated_delivery_at=shipment.estimated_delivery_at,
                    delivered_at=shipment.delivered_at,
                    events=[{"id": e.id, "status": e.status, "description": e.description,
                             "event_at": e.event_at} for e in events]).model_dump(mode="json"))
        return {"ticket_id": ticket.id, "intent": category,
                "order": {"id": order.id, "fulfillment_status": order.fulfillment_status,
                          "tracking_number": order.tracking_number, "total_cents": order.total_cents,
                          "currency": order.currency, "placed_at": order.placed_at,
                          "delivered_at": order.delivered_at} if order else None,
                "line_items": [x.model_dump() for x in lines_for(db, actor, order.id)] if order else [],
                "policies": [{"id": p.id, "title": p.title, "content": p.content,
                              "version": p.version} for p in policies],
                "shipments": shipments}

    @router.get("/customer/tickets/{ticket_id}/messages", response_model=list[MessageView])
    def messages(ticket_id: str, actor: Actor = Depends(customer_actor),
                 db: Session = Depends(db_session)):
        own_ticket(db, actor, ticket_id)
        # Never show internal prompts, AI drafts, or staff-only review comments.
        return db.scalars(select(Message).where(
            Message.tenant_id == actor.tenant_id, Message.ticket_id == ticket_id,
            Message.delivery_status.in_(["received", "customer_ai_response"])
        ).order_by(Message.created_at, Message.id)).all()

    @router.post("/customer/tickets/{ticket_id}/chat")
    def customer_chat(ticket_id: str, payload: AgentChatRequest,
                      actor: Actor = Depends(customer_actor), db: Session = Depends(db_session)):
        ticket = own_ticket(db, actor, ticket_id)
        history = db.scalars(select(Message).where(
            Message.tenant_id == actor.tenant_id, Message.ticket_id == ticket_id,
            Message.delivery_status.in_(["received", "customer_ai_response"])
        ).order_by(Message.created_at, Message.id)).all()
        prior = [{"role": "user" if h.sender == "customer" else "assistant",
                  "content": h.body} for h in history][-8:]
        try:
            result = support_agent.invoke(db, actor, ticket, payload.message, prior)
        except Exception:
            raise HTTPException(503, "Support assistant unavailable; no action was executed") from None
        reply = result["draft"]
        is_exchange = classify(payload.message) == "exchanges"
        tools_ok = {row["tool"] for row in result["tool_trace"] if row["status"] == "ok"}
        if is_exchange and not {"get_order", "search_policies", "get_exchange_options"}.issubset(tools_ok):
            reply = ("I can help with a size exchange, but I cannot verify all the required "
                     "order, policy and stock details yet. Please request human review. "
                     "No exchange has been approved or processed.")
        db.add(Message(id=str(uuid4()), tenant_id=actor.tenant_id, ticket_id=ticket.id,
                       sender="customer", body=payload.message, delivery_status="received"))
        db.add(Message(id=str(uuid4()), tenant_id=actor.tenant_id, ticket_id=ticket.id,
                       sender="staff", body=reply, delivery_status="customer_ai_response"))
        for entry in result["tool_trace"]:
            if entry["tool"] in TOOL_SCHEMAS:
                audit(db, actor, "customer_agent_tool_invoked", ticket.id,
                      tool=entry["tool"], status=entry["status"])
        audit(db, actor, "customer_agent_replied", ticket.id, model_mode=result["model_mode"])
        db.commit()
        return {"ticket_id": ticket.id, "reply": reply,
                "model_mode": result["model_mode"], "status": "assistant_replied",
                "transaction_executed": False, "cart_proposal": result.get("cart_proposal"),
                "tool_trace": result["tool_trace"]}

    @router.post("/customer/tickets/{ticket_id}/exchange-preview", response_model=ExchangeCheckView)
    def exchange_preview(ticket_id: str, payload: ExchangeCheckRequest,
                         actor: Actor = Depends(customer_actor), db: Session = Depends(db_session)):
        ticket = own_ticket(db, actor, ticket_id)
        # Customer cannot claim staff verification through a crafted payload.
        return exchange_check(db, actor, ticket, ExchangeCheckRequest(
            order_line_id=payload.order_line_id,
            target_variant_id=payload.target_variant_id, item_condition="unknown"))

    @router.post("/customer/tickets/{ticket_id}/exchange-request", response_model=ExchangeActionView, status_code=201)
    def request_exchange(ticket_id: str, payload: CustomerExchangeRequest,
                         actor: Actor = Depends(customer_actor), db: Session = Depends(db_session)):
        ticket = own_ticket(db, actor, ticket_id)
        if not payload.confirmed or not payload.condition_attested:
            raise HTTPException(422, "Explicit confirmation and item-condition declaration required")
        check = exchange_check(db, actor, ticket, ExchangeCheckRequest(
            order_line_id=payload.order_line_id, target_variant_id=payload.target_variant_id,
            item_condition="unknown"))
        # The unverified staff-condition check is the only allowed failed check.
        if not all(value for key, value in check.checks.items() if key != "staff_condition_attested"):
            raise HTTPException(422, {"message": "Exchange not eligible", "reasons": check.reasons})
        canonical = json.dumps({"ticket_id": ticket.id, "order_line_id": payload.order_line_id,
                  "target_variant_id": payload.target_variant_id,
                  "condition_attested": payload.condition_attested}, sort_keys=True)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        existing = db.scalar(select(ExchangeRequest).where(
            ExchangeRequest.tenant_id == actor.tenant_id,
            ExchangeRequest.idempotency_key == payload.idempotency_key))
        if existing:
            if existing.payload_hash != digest or existing.ticket_id != ticket.id:
                raise HTTPException(409, "Conflicting idempotency key")
            return existing
        duplicate = db.scalar(select(ExchangeRequest).where(
            ExchangeRequest.tenant_id == actor.tenant_id,
            ExchangeRequest.order_line_id == payload.order_line_id,
            ExchangeRequest.status.in_(["pending_staff_review", "pending_customer_confirmation",
                        "pending_approval", "approved_not_executed", "inventory_reserved"])))
        if duplicate:
            raise HTTPException(409, "An active request already exists for this item")
        request = ExchangeRequest(id=str(uuid4()), tenant_id=actor.tenant_id,
            ticket_id=ticket.id, order_id=check.order_id,
            order_line_id=payload.order_line_id, target_variant_id=payload.target_variant_id,
            item_condition="unknown", policy_version=POLICY_REF,
            reason="Customer requested size exchange; customer declared unworn with tags; staff verification pending",
            idempotency_key=payload.idempotency_key, payload_hash=digest,
            status="pending_staff_review", created_by=actor.id)
        db.add(request)
        db.flush()
        db.add(ExchangeConfirmation(id=str(uuid4()), tenant_id=actor.tenant_id,
               exchange_request_id=request.id, customer_id=actor.customer_id,
               target_variant_id=request.target_variant_id))
        ticket.status = "awaiting_staff_review"
        audit(db, actor, "customer_exchange_requested", request.id,
              target_variant_id=payload.target_variant_id, policy_version=POLICY_REF)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            retried = db.scalar(select(ExchangeRequest).where(
                ExchangeRequest.tenant_id == actor.tenant_id,
                ExchangeRequest.idempotency_key == payload.idempotency_key))
            if retried and retried.payload_hash == digest:
                return retried
            raise HTTPException(409, "Exchange request conflict")
        db.refresh(request)
        return request

    @router.get("/customer/exchange-requests", response_model=list[ExchangeActionView])
    def my_exchanges(actor: Actor = Depends(customer_actor), db: Session = Depends(db_session)):
        # Join the customer-owned tickets; never query by unverified customer ID input.
        return db.scalars(select(ExchangeRequest).join(Ticket, ExchangeRequest.ticket_id == Ticket.id)
            .where(ExchangeRequest.tenant_id == actor.tenant_id,
                   Ticket.tenant_id == actor.tenant_id,
                   Ticket.customer_id == actor.customer_id)
            .order_by(ExchangeRequest.created_at.desc())).all()

    @router.get("/customer/exchange-requests/{request_id}/status")
    def exchange_status(request_id: str, actor: Actor = Depends(customer_actor),
                        db: Session = Depends(db_session)):
        req = db.scalar(select(ExchangeRequest).join(Ticket, ExchangeRequest.ticket_id == Ticket.id)
            .where(ExchangeRequest.id == request_id, ExchangeRequest.tenant_id == actor.tenant_id,
                   Ticket.tenant_id == actor.tenant_id, Ticket.customer_id == actor.customer_id))
        if req is None:
            raise HTTPException(404, "Exchange request not found")
        record = db.scalar(select(ExchangeRecord).where(
            ExchangeRecord.exchange_request_id == req.id, ExchangeRecord.tenant_id == actor.tenant_id))
        return {"reference": req.id, "status": req.status,
                "record_status": record.status if record else None,
                "record_reference": record.id if record else None,
                "replacement_variant_id": req.target_variant_id,
                "note": "Local sandbox only; no Shopify fulfillment or shipment"}

    app.include_router(router)

    # Distinct staff review: customer declaration is NOT staff condition verification.
    @app.post("/exchange-proposals/{action_id}/verify-condition", response_model=ExchangeActionView,
              tags=["Support staff"])
    def verify_condition(action_id: str, payload: VerifyConditionRequest,
                         actor: Actor = Depends(authenticate), db: Session = Depends(db_session)):
        require_role(actor, "agent")
        req = db.scalar(select(ExchangeRequest).where(
            ExchangeRequest.id == action_id, ExchangeRequest.tenant_id == actor.tenant_id))
        if req is None:
            raise HTTPException(404, "Exchange request not found")
        if req.status != "pending_staff_review":
            raise HTTPException(409, "Request is not awaiting staff review")
        ticket = get_ticket(db, actor, req.ticket_id)
        if not payload.verified_unworn_with_tags:
            req.status = "rejected_condition"
            ticket.status = "escalated"
            audit(db, actor, "exchange_condition_rejected", req.id)
        else:
            check = exchange_check(db, actor, ticket, ExchangeCheckRequest(
                order_line_id=req.order_line_id, target_variant_id=req.target_variant_id,
                item_condition="unworn_with_tags"))
            if not check.eligible_for_proposal:
                raise HTTPException(409, {"message": "Exchange no longer eligible", "reasons": check.reasons})
            req.item_condition = "unworn_with_tags"
            req.status = "pending_approval"
            ticket.status = "awaiting_manager_approval"
            audit(db, actor, "exchange_condition_staff_verified", req.id,
                  policy_version=req.policy_version)
        db.commit()
        db.refresh(req)
        return req

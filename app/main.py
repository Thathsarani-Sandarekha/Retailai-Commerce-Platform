"""Shared Northstar Athletics business API: one agent, two local demo applications."""
import hashlib
import json
import os
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import Actor, authenticate, authenticate_staff, require_role
from .agent import SingleAgent, LANGGRAPH_AVAILABLE, TOOL_SCHEMAS
from .customer import mount_customer_routes
from .db import Base, make_engine, make_session_factory
from .models import (ActionRequest, AuditEvent, Customer, ExchangeConfirmation, ExchangeRecord, ExchangeRequest, Message, Order,
                     OrderLine, Product, ProductVariant, Shipment, ShipmentEvent, Ticket)
from .schemas import (AgentChatRequest, AgentChatResponse, ActionView, EvidenceContext, ExchangeCheckRequest, ExchangeCheckView,
                      ExchangeConfirmationCreate, ExchangeConfirmationView, ExchangeRecordView,
                      ExchangeProposalCreate, ExchangeActionView, MessageCreate, MessageView,
                      OrderLineView, ProductCatalogView, RefundProposalCreate, ShipmentView,
                      TicketCreate, TicketView)
from .seed import seed_demo
from .retail_catalog import seed_retail_catalog
from .cart import mount_cart_routes
from .checkout import mount_checkout_routes
from .operations_insights import mount_operations_insights
from .operations_management import mount_operations_management
from .styling import mount_styling_routes, mount_three_looks_routes
from .style_rescue import mount_rescue_routes
from .catalog import search_catalog
from .integrations.shopify import mount_shopify_routes
from .integrations.storage import mount_storage_routes
from .services import audit, classify, get_authorized_order, get_ticket, matching_policies
from .exchanges import exchange_check, POLICY_REF


def create_app(database_url: str | None = None, agent_model=None) -> FastAPI:
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./sportswear_demo.db")
    engine = make_engine(url)
    SessionLocal = make_session_factory(engine)
    support_agent = SingleAgent(model=agent_model)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # SQLite remains an easy, zero-migration local demo. Managed PostgreSQL
        # uses Alembic migrations and never silently creates a production schema.
        if engine.dialect.name == "sqlite":
            Base.metadata.create_all(engine)
        elif not inspect(engine).has_table("alembic_version"):
            raise RuntimeError("Database schema is not migrated: run alembic upgrade head")
        seed_setting = os.getenv("RETAILAI_SEED_DEMO_DATA")
        seed_enabled = (engine.dialect.name == "sqlite") if seed_setting is None else (
            seed_setting.strip().lower() in ("1", "true", "yes"))
        if seed_enabled:
            with SessionLocal() as session:
                seed_demo(session)
                seed_retail_catalog(session)
        yield
        engine.dispose()

    app = FastAPI(title="Northstar Athletics Two-Sided Support API", version="0.4.0", lifespan=lifespan,
                  description="Single tool-using support agent, local business sandbox and approval-gated exchanges. No live Shopify.")

    def db_session():
        with SessionLocal() as session:
            yield session

    @app.get("/health")
    def health():
        return {"status": "ok", "stage": "4a", "mode": "synthetic_sandbox", "brand": "Northstar Athletics (fictional)", "model_mode": support_agent.model.mode, "langgraph_active": LANGGRAPH_AVAILABLE, "shopify_live": os.getenv("SHOPIFY_ADAPTER", "local").lower() == "shopify"}

    def get_lines(db: Session, tenant_id: str, order_id: str) -> list[OrderLineView]:
        lines = db.scalars(select(OrderLine).where(OrderLine.tenant_id == tenant_id,
                           OrderLine.order_id == order_id).order_by(OrderLine.id)).all()
        result = []
        for line in lines:
            variant = db.scalar(select(ProductVariant).where(ProductVariant.id == line.variant_id,
                                ProductVariant.tenant_id == tenant_id))
            product = db.scalar(select(Product).where(Product.id == variant.product_id,
                                Product.tenant_id == tenant_id))
            result.append(OrderLineView(id=line.id, product_id=product.id, product_title=product.title,
                         variant_id=variant.id, size=variant.size, color=variant.color,
                         quantity=line.quantity, final_sale=line.final_sale))
        return result

    def get_shipments(db: Session, tenant_id: str, order_id: str) -> list[ShipmentView]:
        shipments = db.scalars(select(Shipment).where(Shipment.tenant_id == tenant_id,
                               Shipment.order_id == order_id).order_by(Shipment.id)).all()
        result = []
        for shipment in shipments:
            events = db.scalars(select(ShipmentEvent).where(ShipmentEvent.shipment_id == shipment.id,
                                ShipmentEvent.tenant_id == tenant_id).order_by(ShipmentEvent.event_at)).all()
            result.append(ShipmentView(id=shipment.id, carrier=shipment.carrier,
                          tracking_number=shipment.tracking_number, status=shipment.status,
                          estimated_delivery_at=shipment.estimated_delivery_at,
                          delivered_at=shipment.delivered_at,
                          events=[{"id": event.id, "status": event.status,
                                   "description": event.description, "event_at": event.event_at}
                                  for event in events]))
        return result

    @app.get("/catalog", response_model=list[ProductCatalogView])
    def catalog(
        q: str | None = Query(default=None, max_length=80),
        category: str | None = Query(default=None, max_length=40),
        size: str | None = Query(default=None, max_length=20),
        color: str | None = Query(default=None, max_length=40),
        min_price_cents: int | None = Query(default=None, ge=0),
        max_price_cents: int | None = Query(default=None, ge=0),
        in_stock: bool = False,
        actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session),
    ):
        if (min_price_cents is not None and max_price_cents is not None
                and min_price_cents > max_price_cents):
            raise HTTPException(422, "min_price_cents cannot exceed max_price_cents")
        return search_catalog(db, actor.tenant_id, q=q, category=category,
            size=size, color=color, min_price_cents=min_price_cents,
            max_price_cents=max_price_cents, in_stock=in_stock)

    @app.get("/orders/{order_id}/tracking", response_model=list[ShipmentView])
    def order_tracking(order_id: str, actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        order = db.scalar(select(Order).where(Order.id == order_id, Order.tenant_id == actor.tenant_id))
        if not order:
            raise HTTPException(404, "Order not found")
        return get_shipments(db, actor.tenant_id, order.id)

    @app.get("/tickets", response_model=list[TicketView])
    def list_tickets(actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        return db.scalars(select(Ticket).where(Ticket.tenant_id == actor.tenant_id).order_by(Ticket.created_at.desc())).all()

    @app.post("/tickets", response_model=TicketView, status_code=201)
    def create_ticket(payload: TicketCreate, actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        customer = db.scalar(select(Customer).where(Customer.id == payload.customer_id,
                                                    Customer.tenant_id == actor.tenant_id))
        if customer is None:
            raise HTTPException(404, "Customer not found")
        if payload.order_id:
            order = db.scalar(select(Order).where(Order.id == payload.order_id,
                      Order.tenant_id == actor.tenant_id, Order.customer_id == payload.customer_id))
            if order is None:
                raise HTTPException(404, "Order not found for this customer")
        ticket = Ticket(id=str(uuid4()), tenant_id=actor.tenant_id, customer_id=payload.customer_id,
                        order_id=payload.order_id, subject=payload.subject, content=payload.content,
                        intent="unclassified", status="open")
        db.add(ticket)
        db.flush()
        db.add(Message(id=str(uuid4()), tenant_id=actor.tenant_id, ticket_id=ticket.id,
                       sender="customer", body=payload.content, delivery_status="received"))
        audit(db, actor, "ticket_created", ticket.id)
        db.commit()
        db.refresh(ticket)
        return ticket

    @app.get("/tickets/{ticket_id}", response_model=TicketView)
    def read_ticket(ticket_id: str, actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        return get_ticket(db, actor, ticket_id)

    @app.post("/tickets/{ticket_id}/triage", response_model=TicketView)
    def triage_ticket(ticket_id: str, actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        ticket = get_ticket(db, actor, ticket_id)
        ticket.intent = classify(f"{ticket.subject}\n{ticket.content}")
        audit(db, actor, "ticket_triaged", ticket.id, intent=ticket.intent)
        db.commit()
        db.refresh(ticket)
        return ticket

    @app.get("/tickets/{ticket_id}/context", response_model=EvidenceContext)
    def ticket_context(ticket_id: str, actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        ticket = get_ticket(db, actor, ticket_id)
        intent = ticket.intent if ticket.intent != "unclassified" else classify(ticket.subject + " " + ticket.content)
        order = get_authorized_order(db, actor, ticket)
        return EvidenceContext(ticket_id=ticket.id, intent=intent,
                               order=order, policies=matching_policies(db, actor, intent),
                               line_items=get_lines(db, actor.tenant_id, order.id) if order else [],
                               shipments=get_shipments(db, actor.tenant_id, order.id) if order else [])

    @app.get("/tickets/{ticket_id}/messages", response_model=list[MessageView])
    def list_messages(ticket_id: str, actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        get_ticket(db, actor, ticket_id)
        return db.scalars(select(Message).where(Message.ticket_id == ticket_id,
               Message.tenant_id == actor.tenant_id).order_by(Message.created_at)).all()

    @app.post("/tickets/{ticket_id}/messages", response_model=MessageView, status_code=201)
    def draft_staff_message(ticket_id: str, payload: MessageCreate, actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        get_ticket(db, actor, ticket_id)
        message = Message(id=str(uuid4()), tenant_id=actor.tenant_id, ticket_id=ticket_id,
                          sender="staff", body=payload.body, delivery_status="draft_only")
        db.add(message)
        audit(db, actor, "staff_draft_created", ticket_id)
        db.commit()
        db.refresh(message)
        return message

    @app.post("/tickets/{ticket_id}/agent/chat", response_model=AgentChatResponse)
    def chat_with_agent(ticket_id: str, payload: AgentChatRequest,
                        actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        """Staff-only agent-assisted drafting; cannot send to customers or execute actions."""
        ticket = get_ticket(db, actor, ticket_id)
        history = db.scalars(select(Message).where(
            Message.ticket_id == ticket.id, Message.tenant_id == actor.tenant_id,
            Message.delivery_status.in_(["agent_prompt", "agent_draft"])
        ).order_by(Message.created_at, Message.id)).all()
        prior = [{"role": "user" if h.delivery_status == "agent_prompt" else "assistant",
                  "content": h.body} for h in history][-8:]
        try:
            result = support_agent.invoke(db, actor, ticket, payload.message, prior)
        except Exception as exc:
            # No internals, provider payload, or customer content in the response/logs.
            raise HTTPException(503, "AI provider unavailable; no action was executed") from None
        db.add(Message(id=str(uuid4()), tenant_id=actor.tenant_id, ticket_id=ticket.id,
                       sender="staff", body=payload.message, delivery_status="agent_prompt"))
        db.add(Message(id=str(uuid4()), tenant_id=actor.tenant_id, ticket_id=ticket.id,
                       sender="staff", body=result["draft"], delivery_status="agent_draft"))
        for t in result["tool_trace"]:
            # Only allowlisted tool identifiers/status are stored in security audit.
            audit(db, actor, "agent_tool_invoked", ticket.id,
                  tool=t["tool"] if t["tool"] in TOOL_SCHEMAS else "blocked_unknown",
                  status=t["status"])
        audit(db, actor, "agent_draft_created", ticket.id, model_mode=result["model_mode"])
        db.commit()
        return AgentChatResponse(ticket_id=ticket.id, **result)

    @app.post("/tickets/{ticket_id}/refund-proposals", response_model=ActionView, status_code=201)
    def propose_refund(ticket_id: str, payload: RefundProposalCreate,
                       actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        require_role(actor, "agent")
        ticket = get_ticket(db, actor, ticket_id)
        order = get_authorized_order(db, actor, ticket)
        if not order:
            raise HTTPException(422, "Ticket must have an authorized linked order")
        canonical = json.dumps({"ticket_id": ticket.id, "order_id": order.id,
                                "amount_cents": payload.amount_cents, "reason": payload.reason}, sort_keys=True)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        existing = db.scalar(select(ActionRequest).where(
            ActionRequest.tenant_id == actor.tenant_id,
            ActionRequest.idempotency_key == payload.idempotency_key))
        if existing is not None:
            if existing.payload_hash != digest:
                raise HTTPException(409, "Idempotency key reused for a different request")
            return existing
        if payload.amount_cents > order.refundable_cents:
            raise HTTPException(422, "Proposed refund exceeds available refundable amount")
        # A proposal is NOT an eligibility determination; policy verification is a later stage.
        action = ActionRequest(id=str(uuid4()), tenant_id=actor.tenant_id,
                               ticket_id=ticket.id, order_id=order.id, kind="refund",
                               amount_cents=payload.amount_cents, reason=payload.reason,
                               idempotency_key=payload.idempotency_key, payload_hash=digest,
                               status="pending_approval", created_by=actor.id)
        db.add(action)
        audit(db, actor, "refund_proposed", action.id, amount_cents=payload.amount_cents,
              currency=order.currency)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # Concurrent requests with the same key can race; return existing if identical.
            existing = db.scalar(select(ActionRequest).where(
                ActionRequest.tenant_id == actor.tenant_id,
                ActionRequest.idempotency_key == payload.idempotency_key))
            if existing and existing.payload_hash == digest:
                return existing
            raise HTTPException(409, "Idempotency conflict")
        db.refresh(action)
        return action

    @app.post("/tickets/{ticket_id}/exchange-check", response_model=ExchangeCheckView)
    def preview_exchange(ticket_id: str, payload: ExchangeCheckRequest,
                         actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        ticket = get_ticket(db, actor, ticket_id)
        return exchange_check(db, actor, ticket, payload)

    @app.post("/tickets/{ticket_id}/exchange-proposals", response_model=ExchangeActionView, status_code=201)
    def propose_exchange(ticket_id: str, payload: ExchangeProposalCreate,
                         actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        require_role(actor, "agent")
        ticket = get_ticket(db, actor, ticket_id)
        canonical = json.dumps({"ticket_id": ticket.id, "order_line_id": payload.order_line_id,
                                "target_variant_id": payload.target_variant_id,
                                "item_condition": payload.item_condition, "reason": payload.reason}, sort_keys=True)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        existing = db.scalar(select(ExchangeRequest).where(ExchangeRequest.tenant_id == actor.tenant_id,
                             ExchangeRequest.idempotency_key == payload.idempotency_key))
        if existing is not None:
            if existing.payload_hash != digest:
                raise HTTPException(409, "Idempotency key reused for another exchange")
            return existing
        check = exchange_check(db, actor, ticket, payload)
        if not check.eligible_for_proposal:
            raise HTTPException(422, {"message": "Exchange checks failed", "reasons": check.reasons})
        duplicate = db.scalar(select(ExchangeRequest).where(
            ExchangeRequest.tenant_id == actor.tenant_id,
            ExchangeRequest.order_line_id == payload.order_line_id,
            ExchangeRequest.status.in_(["pending_customer_confirmation", "pending_approval", "approved_not_executed", "inventory_reserved"])))
        if duplicate:
            raise HTTPException(409, "An active exchange proposal already exists for this order line")
        action = ExchangeRequest(id=str(uuid4()), tenant_id=actor.tenant_id,
                    ticket_id=ticket.id, order_id=check.order_id,
                    order_line_id=payload.order_line_id, target_variant_id=payload.target_variant_id,
                    item_condition=payload.item_condition, policy_version=POLICY_REF,
                    reason=payload.reason, idempotency_key=payload.idempotency_key,
                    payload_hash=digest, status="pending_customer_confirmation", created_by=actor.id)
        db.add(action)
        audit(db, actor, "exchange_proposed", action.id, policy_version=POLICY_REF)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(select(ExchangeRequest).where(ExchangeRequest.tenant_id == actor.tenant_id,
                        ExchangeRequest.idempotency_key == payload.idempotency_key))
            if existing and existing.payload_hash == digest:
                return existing
            raise HTTPException(409, "Exchange idempotency conflict")
        db.refresh(action)
        return action

    @app.get("/exchange-proposals", response_model=list[ExchangeActionView])
    def exchange_proposals(actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        return db.scalars(select(ExchangeRequest).where(ExchangeRequest.tenant_id == actor.tenant_id)
                          .order_by(ExchangeRequest.created_at.desc())).all()

    @app.post("/exchange-proposals/{action_id}/approve", response_model=ExchangeActionView)
    def approve_exchange(action_id: str, actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        require_role(actor, "manager")
        action = db.scalar(select(ExchangeRequest).where(
            ExchangeRequest.id == action_id, ExchangeRequest.tenant_id == actor.tenant_id))
        if not action:
            raise HTTPException(404, "Exchange request not found")
        if action.status != "pending_approval":
            raise HTTPException(409, "Exchange request not ready for manager approval")
        confirmation = db.scalar(select(ExchangeConfirmation).where(
            ExchangeConfirmation.tenant_id == actor.tenant_id,
            ExchangeConfirmation.exchange_request_id == action.id,
            ExchangeConfirmation.target_variant_id == action.target_variant_id))
        if confirmation is None:
            raise HTTPException(409, "Verified customer confirmation required")
        if action.created_by == actor.id:
            raise HTTPException(403, "Self-approval forbidden")
        ticket = get_ticket(db, actor, action.ticket_id)
        checked = exchange_check(db, actor, ticket, ExchangeCheckRequest(
            order_line_id=action.order_line_id, target_variant_id=action.target_variant_id,
            item_condition=action.item_condition))
        if not checked.eligible_for_proposal:
            raise HTTPException(409, {"message": "Exchange eligibility changed", "reasons": checked.reasons})
        action.status = "approved_not_executed"  # Execution remains a SEPARATE protected operation.
        action.approved_by = actor.id
        audit(db, actor, "exchange_approved_not_executed", action.id, policy_version=action.policy_version)
        db.commit()
        db.refresh(action)
        return action

    @app.post("/exchange-proposals/{action_id}/customer-confirm", response_model=ExchangeConfirmationView)
    def confirm_exchange(action_id: str, payload: ExchangeConfirmationCreate,
                         actor: Actor = Depends(authenticate), db: Session = Depends(db_session)):
        # A staff member or LLM cannot supply a customer_id to impersonate the customer.
        require_role(actor, "customer")
        action = db.scalar(select(ExchangeRequest).where(
            ExchangeRequest.id == action_id, ExchangeRequest.tenant_id == actor.tenant_id))
        if action is None:
            raise HTTPException(404, "Exchange request not found")
        ticket = db.scalar(select(Ticket).where(Ticket.id == action.ticket_id,
                           Ticket.tenant_id == actor.tenant_id, Ticket.customer_id == actor.customer_id))
        if ticket is None:
            raise HTTPException(404, "Exchange request not found")
        if payload.target_variant_id != action.target_variant_id:
            raise HTTPException(409, "Confirmed size does not match the proposed variant")
        existing = db.scalar(select(ExchangeConfirmation).where(
            ExchangeConfirmation.exchange_request_id == action.id,
            ExchangeConfirmation.tenant_id == actor.tenant_id))
        if existing:
            if existing.customer_id == actor.customer_id and existing.target_variant_id == payload.target_variant_id:
                return existing  # An identical customer retry does not create a second confirmation.
            raise HTTPException(409, "Conflicting confirmation")
        if action.status not in ("pending_customer_confirmation", "pending_approval"):
            raise HTTPException(409, "Exchange cannot be confirmed in its current state")
        confirmation = ExchangeConfirmation(id=str(uuid4()), tenant_id=actor.tenant_id,
                exchange_request_id=action.id, customer_id=actor.customer_id,
                target_variant_id=payload.target_variant_id)
        db.add(confirmation)
        action.status = "pending_approval"
        audit(db, actor, "exchange_customer_confirmed", action.id,
              target_variant_id=action.target_variant_id)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(select(ExchangeConfirmation).where(
                ExchangeConfirmation.exchange_request_id == action.id,
                ExchangeConfirmation.tenant_id == actor.tenant_id))
            if existing and existing.customer_id == actor.customer_id and existing.target_variant_id == payload.target_variant_id:
                return existing
            raise HTTPException(409, "Conflicting customer confirmation")
        db.refresh(confirmation)
        return confirmation

    @app.get("/exchange-proposals/{action_id}/confirmation", response_model=ExchangeConfirmationView)
    def read_exchange_confirmation(action_id: str, actor: Actor = Depends(authenticate_staff),
                                   db: Session = Depends(db_session)):
        action = db.scalar(select(ExchangeRequest).where(
            ExchangeRequest.id == action_id, ExchangeRequest.tenant_id == actor.tenant_id))
        if action is None:
            raise HTTPException(404, "Exchange request not found")
        confirmation = db.scalar(select(ExchangeConfirmation).where(
            ExchangeConfirmation.exchange_request_id == action.id,
            ExchangeConfirmation.tenant_id == actor.tenant_id))
        if confirmation is None:
            raise HTTPException(404, "Customer confirmation not yet received")
        return confirmation

    @app.post("/exchange-proposals/{action_id}/execute-local", response_model=ExchangeRecordView,
              status_code=201)
    def execute_exchange_local(action_id: str, actor: Actor = Depends(authenticate_staff),
                               db: Session = Depends(db_session)):
        """Atomic local inventory reservation, not a Shopify exchange or fulfillment."""
        require_role(actor, "manager")
        action = db.scalar(select(ExchangeRequest).where(
            ExchangeRequest.id == action_id, ExchangeRequest.tenant_id == actor.tenant_id))
        if action is None:
            raise HTTPException(404, "Exchange request not found")
        existing = db.scalar(select(ExchangeRecord).where(
            ExchangeRecord.tenant_id == actor.tenant_id,
            ExchangeRecord.exchange_request_id == action.id))
        if existing is not None:
            return existing  # Idempotent replay: never decrement inventory twice.
        if action.status != "approved_not_executed":
            raise HTTPException(409, "Customer confirmation and manager approval required")
        confirmation = db.scalar(select(ExchangeConfirmation).where(
            ExchangeConfirmation.exchange_request_id == action.id,
            ExchangeConfirmation.tenant_id == actor.tenant_id,
            ExchangeConfirmation.target_variant_id == action.target_variant_id))
        if confirmation is None:
            raise HTTPException(409, "Customer confirmation missing")
        ticket = get_ticket(db, actor, action.ticket_id)
        if ticket.customer_id != confirmation.customer_id:
            raise HTTPException(409, "Customer confirmation does not match this order")
        checked = exchange_check(db, actor, ticket, ExchangeCheckRequest(
            order_line_id=action.order_line_id, target_variant_id=action.target_variant_id,
            item_condition=action.item_condition))
        if not checked.eligible_for_proposal:
            raise HTTPException(409, {"message": "Exchange eligibility changed", "reasons": checked.reasons})
        line = db.scalar(select(OrderLine).where(OrderLine.id == action.order_line_id,
                         OrderLine.tenant_id == actor.tenant_id, OrderLine.order_id == action.order_id))
        if line is None:
            raise HTTPException(404, "Original order line missing")
        # SQL conditional writes are in the SAME database transaction. On any failure,
        # rollback restores both the action state and the inventory. Postgres can use
        # row-level locks; SQLite is a local, single-writer demo database.
        claimed = db.execute(update(ExchangeRequest).where(
            ExchangeRequest.id == action.id,
            ExchangeRequest.tenant_id == actor.tenant_id,
            ExchangeRequest.status == "approved_not_executed").values(
                status="inventory_reserved").execution_options(synchronize_session=False))
        if claimed.rowcount != 1:
            db.rollback()
            existing = db.scalar(select(ExchangeRecord).where(
                ExchangeRecord.tenant_id == actor.tenant_id,
                ExchangeRecord.exchange_request_id == action_id))
            if existing:
                return existing
            raise HTTPException(409, "Exchange already being processed")
        reserved = db.execute(update(ProductVariant).where(
            ProductVariant.id == action.target_variant_id,
            ProductVariant.tenant_id == actor.tenant_id,
            ProductVariant.available_quantity >= line.quantity).values(
                available_quantity=ProductVariant.available_quantity - line.quantity
            ).execution_options(synchronize_session=False))
        if reserved.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Replacement stock no longer available")
        record = ExchangeRecord(id=str(uuid4()), tenant_id=actor.tenant_id,
                exchange_request_id=action.id, order_id=action.order_id,
                order_line_id=line.id, source_variant_id=line.variant_id,
                target_variant_id=action.target_variant_id, quantity=line.quantity,
                status="reserved_awaiting_return")
        db.add(record)
        ticket.status = "exchange_processing"
        audit(db, actor, "exchange_inventory_reserved_local", action.id,
              target_variant_id=action.target_variant_id, quantity=line.quantity)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(select(ExchangeRecord).where(
                ExchangeRecord.tenant_id == actor.tenant_id,
                ExchangeRecord.exchange_request_id == action_id))
            if existing:
                return existing
            raise HTTPException(409, "Exchange execution conflict")
        db.refresh(record)
        return record

    @app.get("/orders/{order_id}/exchanges", response_model=list[ExchangeRecordView])
    def order_exchanges(order_id: str, actor: Actor = Depends(authenticate_staff),
                        db: Session = Depends(db_session)):
        order = db.scalar(select(Order).where(Order.id == order_id,
                          Order.tenant_id == actor.tenant_id))
        if order is None:
            raise HTTPException(404, "Order not found")
        return db.scalars(select(ExchangeRecord).where(
            ExchangeRecord.tenant_id == actor.tenant_id,
            ExchangeRecord.order_id == order.id).order_by(ExchangeRecord.reserved_at.desc())).all()

    @app.get("/refund-proposals", response_model=list[ActionView])
    def list_refund_proposals(actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        return db.scalars(select(ActionRequest).where(ActionRequest.tenant_id == actor.tenant_id)
                          .order_by(ActionRequest.created_at.desc())).all()

    @app.post("/refund-proposals/{action_id}/approve", response_model=ActionView)
    def approve_refund(action_id: str, actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        require_role(actor, "manager")
        action = db.scalar(select(ActionRequest).where(
            ActionRequest.id == action_id, ActionRequest.tenant_id == actor.tenant_id))
        if not action:
            raise HTTPException(404, "Action not found")
        if action.status != "pending_approval":
            raise HTTPException(409, "Action is not pending approval")
        if action.created_by == actor.id:
            raise HTTPException(403, "Self-approval forbidden")
        # Approval is persisted; NO Shopify call or financial movement in Stage 1.
        action.status = "approved_not_executed"
        action.approved_by = actor.id
        audit(db, actor, "refund_approved_not_executed", action.id)
        db.commit()
        db.refresh(action)
        return action

    @app.get("/analytics/overview")
    def analytics(actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        ticket_rows = db.execute(select(Ticket.intent, func.count()).where(
            Ticket.tenant_id == actor.tenant_id).group_by(Ticket.intent)).all()
        status_rows = db.execute(select(Ticket.status, func.count()).where(
            Ticket.tenant_id == actor.tenant_id).group_by(Ticket.status)).all()
        action_rows = db.execute(select(ActionRequest.status, func.count()).where(
            ActionRequest.tenant_id == actor.tenant_id).group_by(ActionRequest.status)).all()
        exchange_rows = db.execute(select(ExchangeRequest.status, func.count()).where(
            ExchangeRequest.tenant_id == actor.tenant_id).group_by(ExchangeRequest.status)).all()
        return {"tickets_by_intent": dict(ticket_rows), "tickets_by_status": dict(status_rows),
                "refund_proposals_by_status": dict(action_rows),
                "exchange_proposals_by_status": dict(exchange_rows)}

    @app.get("/audit-events")
    def audit_events(actor: Actor = Depends(authenticate_staff), db: Session = Depends(db_session)):
        require_role(actor, "manager")
        events = db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == actor.tenant_id)
                            .order_by(AuditEvent.created_at.desc()).limit(100)).all()
        return [{"event": a.event, "actor_id": a.actor_id, "resource_id": a.resource_id,
                 "details": a.details, "created_at": a.created_at} for a in events]

    mount_shopify_routes(app, db_session)
    mount_storage_routes(app, db_session)
    mount_customer_routes(app, db_session, support_agent)
    mount_cart_routes(app, db_session)
    mount_checkout_routes(app, db_session)
    mount_operations_insights(app, db_session)
    mount_operations_management(app, db_session)
    mount_styling_routes(app, db_session)
    mount_three_looks_routes(app, db_session)
    mount_rescue_routes(app, db_session)
    return app


app = create_app()

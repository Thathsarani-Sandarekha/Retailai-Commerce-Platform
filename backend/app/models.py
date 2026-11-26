from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .core.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_customer_tenant_id"),)
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    fulfillment_status: Mapped[str] = mapped_column(String(30), nullable=False)
    tracking_number: Mapped[str | None] = mapped_column(String(80))
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    refundable_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    exchangeable: Mapped[bool] = mapped_column(nullable=False, default=True)


class ProductVariant(Base):
    __tablename__ = "product_variants"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(40), nullable=False)
    size: Mapped[str] = mapped_column(String(20), nullable=False)
    color: Mapped[str] = mapped_column(String(40), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False)


class OrderLine(Base):
    __tablename__ = "order_lines"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    final_sale: Mapped[bool] = mapped_column(nullable=False, default=False)


class Shipment(Base):
    __tablename__ = "shipments"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    carrier: Mapped[str] = mapped_column(String(60), nullable=False)
    tracking_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(35), nullable=False)
    estimated_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(35), nullable=False)
    description: Mapped[str] = mapped_column(String(180), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(25), nullable=False)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"))
    subject: Mapped[str] = mapped_column(String(150), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(40), nullable=False, default="unclassified")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    sender: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(30), nullable=False, default="received")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ActionRequest(Base):
    __tablename__ = "action_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_action_tenant_key"),)
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(25), nullable=False, default="pending_approval")
    created_by: Mapped[str] = mapped_column(String(60), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ExchangeRequest(Base):
    __tablename__ = "exchange_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_exchange_tenant_key"),)
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    order_line_id: Mapped[str] = mapped_column(ForeignKey("order_lines.id"), nullable=False)
    target_variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"), nullable=False)
    item_condition: Mapped[str] = mapped_column(String(35), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_approval")
    created_by: Mapped[str] = mapped_column(String(60), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ExchangeConfirmation(Base):
    """Customer explicitly confirmed the specific proposed target variant."""
    __tablename__ = "exchange_confirmations"
    __table_args__ = (UniqueConstraint("tenant_id", "exchange_request_id", name="uq_confirmation_exchange"),)
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    exchange_request_id: Mapped[str] = mapped_column(ForeignKey("exchange_requests.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    target_variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ExchangeRecord(Base):
    """Durable local sandbox exchange and reserved replacement stock, NOT Shopify fulfillment."""
    __tablename__ = "exchange_records"
    __table_args__ = (UniqueConstraint("tenant_id", "exchange_request_id", name="uq_record_exchange"),)
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    exchange_request_id: Mapped[str] = mapped_column(ForeignKey("exchange_requests.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    order_line_id: Mapped[str] = mapped_column(ForeignKey("order_lines.id"), nullable=False)
    source_variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"), nullable=False)
    target_variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="reserved_awaiting_return")
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(60), nullable=False)
    event: Mapped[str] = mapped_column(String(70), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(60), nullable=False)
    # Only pre-approved structured metadata; never customer message, names or email.
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CartItem(Base):
    """Persisted shopping intent, not reserved stock or a completed order."""
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("tenant_id", "customer_id", "variant_id", name="uq_cart_customer_variant"),)
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CartMutation(Base):
    """Idempotency ledger for additive cart mutations."""
    __tablename__ = "cart_mutations"
    __table_args__ = (UniqueConstraint("tenant_id", "customer_id", "idempotency_key", name="uq_cart_mutation_key"),)
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CheckoutReceipt(Base):
    """Idempotent proof of a synthetic, unpaid local order creation."""
    __tablename__ = "checkout_receipts"
    __table_args__ = (UniqueConstraint("tenant_id", "customer_id", "idempotency_key", name="uq_checkout_customer_key"),
                      UniqueConstraint("tenant_id", "order_id", name="uq_checkout_order"))
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    quote_token: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    items_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="sandbox_order_created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

class TicketWorkItem(Base):
    """Additive staff ownership metadata; preserves existing SQLite ticket schemas."""
    __tablename__ = "ticket_work_items"
    id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(12), nullable=False, default="normal")
    assigned_to: Mapped[str | None] = mapped_column(String(60))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

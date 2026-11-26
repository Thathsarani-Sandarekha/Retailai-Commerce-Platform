from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class TicketCreate(BaseModel):
    customer_id: str = Field(min_length=1, max_length=60)
    order_id: str | None = Field(default=None, max_length=60)
    subject: str = Field(min_length=3, max_length=150)
    content: str = Field(min_length=5, max_length=6000)


class TicketView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    customer_id: str
    order_id: str | None
    subject: str
    content: str
    intent: str
    status: str
    created_at: datetime


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=6000)


class MessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    sender: Literal["customer", "staff"]
    body: str
    delivery_status: str
    created_at: datetime


class RefundProposalCreate(BaseModel):
    amount_cents: int = Field(gt=0)
    reason: str = Field(min_length=8, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class ActionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ticket_id: str
    order_id: str
    kind: str
    amount_cents: int
    reason: str
    status: str
    created_by: str
    approved_by: str | None


class PolicyView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    content: str
    version: str


class OrderView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    fulfillment_status: str
    tracking_number: str | None
    total_cents: int
    refundable_cents: int
    currency: str
    placed_at: datetime
    delivered_at: datetime | None = None


class EvidenceContext(BaseModel):
    ticket_id: str
    intent: str
    order: OrderView | None
    policies: list[PolicyView]
    line_items: list["OrderLineView"] = Field(default_factory=list)
    shipments: list["ShipmentView"] = Field(default_factory=list)
    note: str = "Read-only deterministic retrieval baseline; not vector RAG or an LLM-generated response."


class ProductVariantView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    product_id: str
    sku: str
    size: str
    color: str
    price_cents: int
    available_quantity: int


class ProductCatalogView(BaseModel):
    id: str
    title: str
    category: str
    description: str
    exchangeable: bool
    variants: list[ProductVariantView]


class OrderLineView(BaseModel):
    id: str
    product_id: str
    product_title: str
    variant_id: str
    size: str
    color: str
    quantity: int
    final_sale: bool


class ShipmentEventView(BaseModel):
    id: str
    status: str
    description: str
    event_at: datetime


class ShipmentView(BaseModel):
    id: str
    carrier: str
    tracking_number: str
    status: str
    estimated_delivery_at: datetime | None
    delivered_at: datetime | None
    events: list[ShipmentEventView]


class ExchangeCheckRequest(BaseModel):
    order_line_id: str = Field(min_length=1, max_length=60)
    target_variant_id: str = Field(min_length=1, max_length=60)
    item_condition: Literal["unknown", "unworn_with_tags", "worn_or_washed"] = "unknown"


class ExchangeProposalCreate(ExchangeCheckRequest):
    reason: str = Field(min_length=8, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class ExchangeCheckView(BaseModel):
    ticket_id: str
    order_id: str
    order_line_id: str
    target_variant_id: str
    eligible_for_proposal: bool
    checks: dict[str, bool]
    reasons: list[str]
    evidence_policy: str
    condition_source: str = "staff-attested field; not independently verified by the demo"


class ExchangeActionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ticket_id: str
    order_id: str
    order_line_id: str
    target_variant_id: str
    item_condition: str
    policy_version: str
    reason: str
    status: str
    created_by: str
    approved_by: str | None


class ExchangeConfirmationCreate(BaseModel):
    confirmed: Literal[True]
    target_variant_id: str = Field(min_length=1, max_length=60)


class ExchangeConfirmationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    exchange_request_id: str
    customer_id: str
    target_variant_id: str
    confirmed_at: datetime


class ExchangeRecordView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    exchange_request_id: str
    order_id: str
    order_line_id: str
    source_variant_id: str
    target_variant_id: str
    quantity: int
    status: str
    reserved_at: datetime


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=3, max_length=2000)


class AgentChatResponse(BaseModel):
    ticket_id: str
    draft: str = Field(min_length=1, max_length=4500)
    model_mode: str
    graph_engine: str
    tool_trace: list[dict[str, str]]
    steps: int
    sent_to_customer: Literal[False]
    transaction_executed: Literal[False]

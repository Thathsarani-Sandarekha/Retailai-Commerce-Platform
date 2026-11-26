export type DemoRole = "staff" | "manager" | "customer-c3";
export interface Ticket { id: string; customer_id: string; order_id: string | null; subject: string; content: string; intent: string; status: string; created_at: string }
export interface Message { id: string; sender: "customer" | "staff"; body: string; delivery_status: string; created_at: string }
export interface Order { id: string; fulfillment_status: string; tracking_number: string | null; total_cents: number; currency: string; placed_at: string; delivered_at: string | null }
export interface OrderLine { id: string; product_id: string; product_title: string; variant_id: string; size: string; color: string; quantity: number; final_sale: boolean }
export interface Policy { id: string; title: string; version: string; content: string }
export interface Shipment { id: string; carrier: string; tracking_number: string; status: string; events: { id: string; status: string; description: string; event_at: string }[] }
export interface EvidenceContext { ticket_id: string; intent: string; order: Order | null; line_items: OrderLine[]; policies: Policy[]; shipments: Shipment[] }
export interface Variant { id: string; product_id: string; sku: string; size: string; color: string; price_cents: number; available_quantity: number }
export interface Product { id: string; title: string; category: string; description: string; exchangeable: boolean; variants: Variant[] }
export interface AgentResponse { ticket_id: string; draft: string; model_mode: string; graph_engine: string; steps: number; tool_trace: { tool: string; status: string }[]; sent_to_customer: false; transaction_executed: false }
export interface ExchangeProposal { id: string; ticket_id: string; order_id: string; order_line_id: string; target_variant_id: string; item_condition: string; policy_version: string; reason: string; status: string; created_by: string; approved_by: string | null }
export interface ExchangeCheck { eligible_for_proposal: boolean; checks: Record<string, boolean>; reasons: string[]; evidence_policy: string; condition_source: string }
export interface ExchangeRecord { id: string; exchange_request_id: string; order_id: string; order_line_id: string; source_variant_id: string; target_variant_id: string; quantity: number; status: string; reserved_at: string }
export interface Analytics { tickets_by_intent: Record<string, number>; tickets_by_status: Record<string, number>; exchange_proposals_by_status: Record<string, number> }

export async function api<T>(path: string, init?: { method?: "GET" | "POST" | "PATCH" | "DELETE"; data?: unknown; role?: DemoRole }): Promise<T> {
  const response = await fetch(`/api/demo${path}`, {
    method: init?.method || "GET",
    headers: { "Content-Type": "application/json", "x-demo-role": init?.role || "staff" },
    body: init?.data === undefined ? undefined : JSON.stringify(init.data),
    cache: "no-store",
  });
  const raw = await response.text();
  let data: unknown;
  try { data = JSON.parse(raw); } catch { data = { detail: raw || `HTTP ${response.status}` }; }
  if (!response.ok) {
    const detail = (data as { detail?: unknown }).detail;
    const message = typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return data as T;
}


export interface CartItem {
  variant_id: string; product_id: string; product_title: string; category: string;
  size: string; color: string; quantity: number; unit_price_cents: number;
  line_total_cents: number; available_quantity: number; stock_ok: boolean;
}
export interface CustomerCart {
  customer_id: string; currency: "USD"; items: CartItem[]; item_count: number;
  subtotal_cents: number; stock_ok: boolean; checkout_enabled: boolean; notice: string;
}


export interface CheckoutPreview {
  quote_token: string; currency: "USD"; items: CartItem[];
  item_count: number; subtotal_cents: number; tax_cents: number;
  shipping_cents: number; total_cents: number; payment_status: "not_charged";
  stock_reserved: false; notice: string;
}
export interface CheckoutReceipt {
  reference: string; order_id: string; status: "sandbox_order_created" | "sandbox_payment_simulated";
  payment_status: "not_charged" | "simulated_paid"; currency: "USD";
  total_cents: number; created_at: string; duplicate_request: boolean;
  items: {variant_id: string; product_title: string; size: string; color: string;
          quantity: number; unit_price_cents: number; line_total_cents: number}[];
  notice: string;
}

export type StaffSandboxOrder = CheckoutReceipt & { customer_id: string };

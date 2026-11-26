"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import {
  ArrowRight, Bot, CheckCircle2, ChevronDown, Headphones, LockKeyhole,
  MessageCircle, Package, RefreshCcw, RotateCcw, Send, ShieldCheck,
  ShoppingBag, Sparkles, Truck, X,
} from "lucide-react";
import { api, type EvidenceContext, type ExchangeProposal, type Message, type Product, type Ticket } from "@/lib/api";
import "./customer-assistant.css";

type Tab = "chat" | "orders" | "human";
type Profile = { id: string; display_name: string; environment: string };
type Order = {
  id: string; status: string; tracking_number: string | null;
  total_cents: number; currency: string;
  items: { id: string; product_title: string; size: string; color: string; quantity: number }[];
};
type CartProposal = {
  action?: "add" | "set_quantity" | "remove_item";
  variant_id: string; product_title: string; size: string; color: string;
  quantity: number; currency: "USD"; unit_price_cents: number;
  line_total_cents: number; available_quantity: number;
  idempotency_key?: string; requires_customer_confirmation: true; cart_updated: false;
};
type ChatResult = { ticket_id: string; reply: string; model_mode: string; transaction_executed: false; cart_proposal: CartProposal | null; tool_trace: {tool: string; status: string}[] };
// Client-only bubble shown while Groq is responding; the server remains the source of truth.
type OptimisticMessage = { ticketId: string; body: string; state: "sending" | "failed" };
type ExchangePreview = {
  checks: Record<string, boolean>; reasons: string[]; eligible_for_proposal: boolean; evidence_policy: string;
};
type ExchangeStatus = {
  reference: string; status: string; record_status: string | null; record_reference: string | null;
};
const customerApi = <T,>(path: string, init?: {method?: "GET" | "POST"; data?: unknown}) =>
  api<T>(path, { ...init, role: "customer-c3" });
const nice = (s: string) => s.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());

export default function CustomerAssistant() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("chat");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [catalog, setCatalog] = useState<Product[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [exchanges, setExchanges] = useState<ExchangeProposal[]>([]);
  const [selectedTicketId, setSelectedTicketId] = useState("N-T3");
  const [context, setContext] = useState<EvidenceContext | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [optimisticMessage, setOptimisticMessage] = useState<OptimisticMessage | null>(null);
  const [input, setInput] = useState("");
  const [cartProposal, setCartProposal] = useState<CartProposal | null>(null);
  const [checkoutHint, setCheckoutHint] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [lineId, setLineId] = useState("");
  const [targetVariantId, setTargetVariantId] = useState("");
  const [preview, setPreview] = useState<ExchangePreview | null>(null);
  const [condition, setCondition] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [status, setStatus] = useState<ExchangeStatus | null>(null);
  const [newSubject, setNewSubject] = useState("");
  const [newMessage, setNewMessage] = useState("");
  const [newTicketOrderId, setNewTicketOrderId] = useState("");
  const [exchangeExpanded, setExchangeExpanded] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const refresh = useCallback(async () => {
    const [person, products, customerOrders, customerTickets, reqs] = await Promise.all([
      customerApi<Profile>("/customer/profile"),
      customerApi<Product[]>("/customer/catalog"),
      customerApi<Order[]>("/customer/orders"),
      customerApi<Ticket[]>("/customer/tickets"),
      customerApi<ExchangeProposal[]>("/customer/exchange-requests"),
    ]);
    setProfile(person); setCatalog(products); setOrders(customerOrders);
    setTickets(customerTickets); setExchanges(reqs);
  }, []);
  const refreshTicket = useCallback(async (id: string) => {
    const [ctx, history] = await Promise.all([
      customerApi<EvidenceContext>(`/customer/tickets/${id}/context`),
      customerApi<Message[]>(`/customer/tickets/${id}/messages`),
    ]);
    setContext(ctx); setMessages(history);
  }, []);

  useEffect(() => { refresh().catch(e => setError(e.message)); }, [refresh]);
  useEffect(() => {
    const onOrder = () => { void refresh(); };
    window.addEventListener("retailai:order-created", onOrder);
    return () => window.removeEventListener("retailai:order-created", onOrder);
  }, [refresh]);
  useEffect(() => {
    let active = true;
    setContext(null); setPreview(null); setLineId(""); setTargetVariantId("");
    setCartProposal(null);
    setConfirmed(false); setCondition(false); setStatus(null); setExchangeExpanded(false);
    Promise.all([
      customerApi<EvidenceContext>(`/customer/tickets/${selectedTicketId}/context`),
      customerApi<Message[]>(`/customer/tickets/${selectedTicketId}/messages`),
    ]).then(([ctx, history]) => {
      if (active) { setContext(ctx); setMessages(history); }
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [selectedTicketId]);

  useEffect(() => {
    const handler = (event: Event) => {
      const orderId = (event as CustomEvent<{ orderId?: string }>).detail?.orderId;
      const relatedTicket = orderId ? tickets.find(t => t.order_id === orderId) : undefined;
      if (relatedTicket) setSelectedTicketId(relatedTicket.id);
      if (orderId) setNewTicketOrderId(orderId);
      setTab(orderId && !relatedTicket ? "human" : "chat");
      setOpen(true);
    };
    window.addEventListener("retailai:open-assistant", handler);
    return () => window.removeEventListener("retailai:open-assistant", handler);
  }, [tickets]);
  useEffect(() => {
    const openOrders = () => { void refresh(); setTab("orders"); setOpen(true); };
    window.addEventListener("retailai:open-orders", openOrders);
    return () => window.removeEventListener("retailai:open-orders", openOrders);
  }, [refresh]);
  useEffect(() => {
    const closeForCart = () => setOpen(false);
    window.addEventListener("retailai:open-cart", closeForCart);
    return () => window.removeEventListener("retailai:open-cart", closeForCart);
  }, []);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
      if (event.key === "Tab" && drawerRef.current) {
        const targets = Array.from(drawerRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), select:not([disabled])'
        ));
        const first = targets[0], last = targets[targets.length - 1];
        if (!first || !last) return;
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener("keydown", onKey);
    closeRef.current?.focus();
    return () => { window.removeEventListener("keydown", onKey); previous?.focus?.(); };
  }, [open]);
  useEffect(() => {
    if (open && tab === "chat") messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, optimisticMessage, busy, open, tab]);

  const activeTicket = tickets.find(t => t.id === selectedTicketId);
  const linkedOrder = orders.find(o => o.id === activeTicket?.order_id);
  const lines = context?.line_items || [];
  const selectedLine = lines.find(x => x.id === lineId) || lines[0];
  const item = catalog.find(p => p.id === selectedLine?.product_id);
  const alternatives = (item?.variants || []).filter(v =>
    v.color === selectedLine?.color && v.id !== selectedLine?.variant_id);
  const variant = alternatives.find(v => v.id === targetVariantId) || alternatives[0];
  const myRequest = exchanges.find(r => r.ticket_id === selectedTicketId);
  const exchangeAllowed = Boolean(preview?.eligible_for_proposal &&
    Object.entries(preview.checks).every(([key, value]) => key === "staff_condition_attested" || value));

  useEffect(() => { // Refresh request status when the ticket/request changes.
    if (!myRequest) { setStatus(null); return; }
    customerApi<ExchangeStatus>(`/customer/exchange-requests/${myRequest.id}/status`)
      .then(setStatus).catch(() => setStatus(null));
  }, [myRequest?.id, myRequest?.status]);

  async function simulatePayment(orderId: string) {
    if (busy) return;
    if (!window.confirm(`Simulate payment for demo order ${orderId}?\n\nNo card details or money will be collected.`)) return;
    setBusy(`payment-${orderId}`); setError(""); setSuccess("");
    try {
      await customerApi(`/customer/checkout/orders/${encodeURIComponent(orderId)}/simulate-payment`,
        { method: "POST", data: { confirmed: true } });
      setSuccess(`Payment marked complete for ${orderId} (simulation only; no real charge).`);
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not simulate payment"); }
    finally { setBusy(""); }
  }

  async function run(action: string, operation: () => Promise<string>) {
    setBusy(action); setError(""); setSuccess("");
    try {
      const result = await operation();
      setSuccess(result);
      await refresh();
      await refreshTicket(selectedTicketId);
    } catch (e) { setError(e instanceof Error ? e.message : "Request failed. Please try again."); }
    finally { setBusy(""); }
  }
  function chooseTicket(id: string) {
    setSelectedTicketId(id); setSuccess(""); setError("");
  }
  function navigate(next: Tab) {
    setTab(next); setError(""); setSuccess("");
    if (next === "chat") requestAnimationFrame(() => inputRef.current?.focus());
  }
  function ask(text: string) {
    setInput(text); setTab("chat"); requestAnimationFrame(() => inputRef.current?.focus());
  }
  async function send() {
    const message = input.trim();
    if (message.length < 3 || busy || !activeTicket) return;
    const ticketId = selectedTicketId;

    // Optimistic UI: clear the composer and render the user's bubble BEFORE the request.
    // This is not persisted chat history; the API response will be reconciled below.
    setOptimisticMessage({ ticketId, body: message, state: "sending" });
    setInput("");
    setBusy("chat");
    setError("");
    setSuccess("");
    setCartProposal(null);
    setCheckoutHint(false);
    try {
      const answer = await customerApi<ChatResult>(`/customer/tickets/${ticketId}/chat`,
        { method: "POST", data: { message } });
      if (answer.transaction_executed) {
        throw new Error("Unexpected transaction reported by read-only assistant");
      }
      setCartProposal(answer.cart_proposal ?? null);
      setCheckoutHint(answer.tool_trace?.some(trace =>
        trace.tool === "get_checkout_preview" && trace.status === "ok") ?? false);

      // Replace the local bubble with the authoritative saved customer + agent messages.
      await refreshTicket(ticketId);
      setOptimisticMessage(null);
      await refresh();
    } catch (e) {
      // Do not silently lose the customer's words if the network or model fails.
      // We cannot assume a failed response means the server did not save the message.
      setOptimisticMessage(prev => prev?.ticketId === ticketId
        ? { ...prev, state: "failed" } : prev);
      setError(`Could not confirm message delivery. Check the conversation before retrying. ${e instanceof Error ? e.message : "Please try again."}`);
    } finally {
      setBusy("");
    }
  }
  async function confirmCartAction() {
    if (!cartProposal || busy) return;
    const current = cartProposal;
    await run("cart", async () => {
      if (current.action === "remove_item") {
        await api(`/customer/cart/items/${encodeURIComponent(current.variant_id)}`,
          { method: "DELETE", role: "customer-c3" });
      } else if (current.action === "set_quantity") {
        await api(`/customer/cart/items/${encodeURIComponent(current.variant_id)}`,
          { method: "PATCH", data: { quantity: current.quantity }, role: "customer-c3" });
      } else {
        await customerApi("/customer/cart/items", { method: "POST", data: {
          variant_id: current.variant_id, quantity: current.quantity,
          idempotency_key: current.idempotency_key,
        } });
      }
      setCartProposal(null);
      window.dispatchEvent(new Event("retailai:cart-updated"));
      setOpen(false);
      window.dispatchEvent(new Event("retailai:open-cart"));
      return `Cart updated after your confirmation: ${current.product_title}. No order or payment created.`;
    });
  }
  async function checkExchange() {
    if (!selectedLine || !variant) return;
    await run("check", async () => {
      const result = await customerApi<ExchangePreview>(`/customer/tickets/${selectedTicketId}/exchange-preview`,
        { method: "POST", data: { order_line_id: selectedLine.id, target_variant_id: variant.id, item_condition: "unknown" } });
      setPreview(result);
      return "Initial policy and stock checks completed. Staff must still verify the item condition.";
    });
  }
  async function submitExchange() {
    if (!selectedLine || !variant || !confirmed || !condition || !exchangeAllowed) return;
    await run("submit", async () => {
      const request = await customerApi<ExchangeProposal>(`/customer/tickets/${selectedTicketId}/exchange-request`,
        { method: "POST", data: {
          order_line_id: selectedLine.id, target_variant_id: variant.id,
          confirmed: true, condition_attested: true,
          idempotency_key: `customer-${selectedTicketId}-${selectedLine.id}-${variant.id}`,
        } });
      return `Request ${request.id} created. Awaiting staff condition review and manager approval.`;
    });
  }
  async function createTicket() {
    if (!profile || newSubject.trim().length < 3 || newMessage.trim().length < 5) return;
    setBusy("ticket"); setError(""); setSuccess("");
    try {
      const ticket = await customerApi<Ticket>("/customer/tickets", { method: "POST", data: {
        customer_id: profile.id, order_id: newTicketOrderId || null,
        subject: newSubject.trim(), content: newMessage.trim(),
      } });
      await refresh();
      chooseTicket(ticket.id);
      setNewSubject(""); setNewMessage(""); setNewTicketOrderId("");
      setSuccess(`Support ticket ${ticket.id} created.`);
      setTab("chat");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not create ticket"); }
    finally { setBusy(""); }
  }
  async function reload() {
    await run("refresh", async () => {
      if (myRequest) {
        const latest = await customerApi<ExchangeStatus>(`/customer/exchange-requests/${myRequest.id}/status`);
        setStatus(latest);
      }
      return "Customer support records refreshed.";
    });
  }

  return <div className="retail-assistant-root">
    {!open && <button className="retail-chat-fab" type="button" aria-label="Open NOVA shopping and style assistant" aria-expanded="false" aria-controls="retail-assistant-drawer" onClick={() => setOpen(true)}>
      <span className="retail-chat-fab-icon ns-bot-fab-icon"><Image src="/images/brand/northstar-bot.webp" alt="" width={74} height={74}/><span className="ns-bot-online"/></span>
      <span className="retail-chat-fab-copy"><strong>Meet NOVA</strong><small>Style, shopping & support</small></span>
    </button>}
    {open && <>
      <button type="button" className="retail-chat-backdrop" aria-label="Close assistant" onClick={() => setOpen(false)}/>
      <div id="retail-assistant-drawer" className="retail-chat-drawer" role="dialog" aria-modal="true" aria-label="NOVA shopping and support assistant" ref={drawerRef}>
        <header className="retail-chat-drawer-header">
          <div className="retail-chat-drawer-brand"><div className="retail-chat-brand-icon"><Sparkles size={21}/></div><div><strong>NORTHSTAR EDIT <span>/ NOVA</span></strong><small><i/> AI SHOPPING & SUPPORT</small></div></div>
          <button type="button" className="retail-chat-icon-button" ref={closeRef} onClick={() => setOpen(false)} aria-label="Close assistant"><X size={21}/></button>
        </header>
        {tab === "chat" && <section className={`ns-chat-mascot-banner ${messages.length > 0 ? "ns-chat-mascot-compact" : ""}`} aria-label="Welcome to Northstar assistant">
          <div className="ns-chat-robot-glow" aria-hidden="true"/>
          <Image className="ns-chat-robot-image" src="/images/brand/northstar-bot.webp" alt="NOVA, the friendly Northstar robot style assistant" width={166} height={166} priority/>
          <div className="ns-chat-robot-copy"><span><Sparkles size={12}/> YOUR AI STYLE CONCIERGE</span><strong>HEY, I'M <em>NOVA.</em></strong><p>Outfits, dresses, denim, accessories, orders. Ask away.</p></div>
        </section>}
        <div className="retail-chat-demo-note"><ShieldCheck size={13}/> Demo assistant · Synthetic orders · Cart actions need confirmation</div>
        <nav className="retail-chat-tabs" aria-label="Assistant functions">
          <button type="button" className={tab === "chat" ? "selected" : ""} onClick={() => navigate("chat")} aria-current={tab === "chat" ? "page" : undefined}><MessageCircle size={15}/> Chat</button>
          <button type="button" className={tab === "orders" ? "selected" : ""} onClick={() => navigate("orders")} aria-current={tab === "orders" ? "page" : undefined}><Package size={15}/> Orders & requests</button>
          <button type="button" className={tab === "human" ? "selected" : ""} onClick={() => navigate("human")} aria-current={tab === "human" ? "page" : undefined}><Headphones size={15}/> Human help</button>
        </nav>
        {error && <div className="retail-chat-feedback error" role="alert">{error}</div>}
        {success && <div className="retail-chat-feedback success" role="status">{success}</div>}
        <div className="retail-chat-select-ticket"><label htmlFor="retail-chat-ticket">Conversation</label><select id="retail-chat-ticket" value={selectedTicketId} disabled={busy === "chat"} onChange={e => chooseTicket(e.target.value)}>{tickets.map(t => <option key={t.id} value={t.id}>{t.subject}</option>)}</select></div>
        {tab === "chat" && <>
          <div className="retail-chat-scroll" ref={messagesRef} aria-live="polite">
            {messages.length === 0 && <div className="retail-chat-intro"><strong>WHAT CAN I FIND FOR YOU?</strong><p>Ask about dresses, denim, bags, outfits, shipping or your orders.</p></div>}
            {messages.map(m => <div key={m.id} className={`retail-chat-bubble ${m.sender === "customer" ? "user" : "assistant"}`}><small>{m.sender === "customer" ? "YOU" : m.sender === "staff" ? "SUPPORT / AI DRAFT" : "SUPPORT"}</small><p>{m.body}</p></div>)}
            {optimisticMessage?.ticketId === selectedTicketId &&
              <div className={`retail-chat-bubble user retail-chat-optimistic ${optimisticMessage.state}`}>
                <small>{optimisticMessage.state === "sending" ? "YOU · Sending…" : "YOU · Delivery not confirmed"}</small>
                <p>{optimisticMessage.body}</p>
                {optimisticMessage.state === "failed" &&
                  <button type="button" className="retail-chat-restore" onClick={() => {
                    setInput(optimisticMessage.body);
                    setOptimisticMessage(null);
                    setError("");
                    inputRef.current?.focus();
                  }}>Restore text to edit</button>}
              </div>}
            {cartProposal && <div className="retail-chat-cart-proposal" role="group" aria-label="Confirm suggested cart item">
              <strong>{cartProposal.action === "remove_item" ? "Ready to remove — confirmation required" :
                cartProposal.action === "set_quantity" ? "Ready to update quantity — confirmation required" :
                "Ready to add — confirmation required"}</strong>
              <p>{cartProposal.product_title} · {cartProposal.size} · {cartProposal.color}</p>
              <p>{cartProposal.quantity} × ${(cartProposal.unit_price_cents / 100).toFixed(2)} = <strong>${(cartProposal.line_total_cents / 100).toFixed(2)}</strong></p>
              <small>Stock is rechecked when you confirm. This does not place an order or reserve stock.</small>
              <div className="retail-chat-cart-actions">
                <button type="button" disabled={!!busy} onClick={() => void confirmCartAction()}><ShoppingBag size={14}/>
                  {cartProposal.action === "remove_item" ? "Confirm removal" :
                   cartProposal.action === "set_quantity" ? "Confirm quantity change" : "Confirm add to cart"}
                </button>
                <button type="button" disabled={!!busy} onClick={() => setCartProposal(null)}>Not now</button>
              </div>
            </div>}
            {checkoutHint && <div className="retail-chat-cart-proposal" role="group" aria-label="Review checkout">
              <strong>Your cart is ready for review</strong>
              <p>Only you can confirm this sandbox order. No payment will be collected.</p>
              <button type="button" onClick={() => {
                setOpen(false); window.dispatchEvent(new Event("retailai:open-cart"));
              }}>Open cart & review checkout</button>
            </div>}
            {busy === "chat" && <div className="retail-chat-typing"><span/><span/><span/> Checking your store records…</div>}
          </div>
          {messages.length === 0 && !optimisticMessage && <div className="retail-chat-suggestions">
            <button type="button" onClick={() => ask("Where is my order?")}>Track my order</button>
            <button type="button" onClick={() => ask("What is the exchange policy?")}>Exchange policy</button>
            <button type="button" onClick={() => ask("Do you have the Solstice Wrap Dress in size M?")}>Find my size</button>
            <button type="button" onClick={() => ask("Find black block heels in US size 8 under $100 and prepare them for my cart")}>Find shoes</button>
            <button type="button" onClick={() => ask("Show my cart and help me place my order")}>Review checkout</button>
          </div>}
          <div className="retail-chat-compose">
            <textarea ref={inputRef} aria-label="Message NOVA" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }} maxLength={2000} rows={2} placeholder="Ask about orders, sizes, delivery or returns…"/>
            <button type="button" aria-label="Send message" disabled={!!busy || input.trim().length < 3} onClick={() => void send()}><Send size={18}/></button>
          </div>
          <div className="retail-chat-disclaimer"><LockKeyhole size={12}/> Replies are informational; requests require explicit confirmation.</div>
        </>}
        {tab === "orders" && <div className="retail-chat-scroll retail-chat-actions">
          <div className="retail-chat-panel-intro"><span>YOUR ACCOUNT</span><h3>Orders & requests</h3><p>View the status of your purchases and submit a protected support request.</p></div>
          {orders.map(o => <div className="retail-chat-order" key={o.id}><div className="retail-chat-order-top"><strong>{o.id}</strong><span>{nice(o.status)}</span></div><p>{o.items.map(x => `${x.product_title} (${x.size})`).join(", ")}</p><small><Truck size={12}/>{o.tracking_number || "Tracking pending"}</small>{o.status === "awaiting_payment_demo" && <button className="retail-chat-demo-pay" type="button" disabled={!!busy} onClick={() => void simulatePayment(o.id)}>{busy === `payment-${o.id}` ? "Recording…" : "Simulate payment (no charge)"}</button>}{o.status === "payment_simulated_demo" && <small className="retail-chat-payment-complete"><CheckCircle2 size={13}/> Payment simulated — no card charged</small>}</div>)}
          <button type="button" className="retail-chat-toggle" aria-expanded={exchangeExpanded} onClick={() => setExchangeExpanded(v => !v)}><span><RotateCcw size={16}/> Request a size exchange</span><ChevronDown size={17}/></button>
          {exchangeExpanded && <div className="retail-chat-exchange-form">
            <p className="retail-chat-muted">Use an order-linked conversation to request a size exchange. Requests are reviewed by staff and managers.</p>
            <div className="retail-chat-row"><span>Linked order</span><strong>{context?.order?.id || "No linked order"}</strong></div>
            {lines.length > 0 && <>
              <label htmlFor="retail-chat-line">Purchased item</label>
              <select id="retail-chat-line" value={selectedLine?.id || ""} onChange={e => { setLineId(e.target.value); setTargetVariantId(""); setPreview(null); }}>{lines.map(x => <option key={x.id} value={x.id}>{x.product_title} · {x.size}</option>)}</select>
              <div className="retail-chat-row"><span>Original size</span><strong>{selectedLine?.size}</strong></div>
              <label htmlFor="retail-chat-variant">Requested variant</label>
              <select id="retail-chat-variant" value={variant?.id || ""} onChange={e => {setTargetVariantId(e.target.value); setPreview(null);}} disabled={!alternatives.length}>
                {alternatives.length === 0 && <option value="">No alternate sizes available</option>}
                {alternatives.map(v => <option key={v.id} value={v.id}>{v.size} · {v.color} · {v.available_quantity} in stock</option>)}
              </select>
              {variant && <div className="retail-chat-stock"><span/>{variant.available_quantity} available · {variant.color}</div>}
              {!myRequest && <button className="retail-chat-action-btn" type="button" onClick={() => void checkExchange()} disabled={!!busy || !variant}>Check policy & availability <ArrowRight size={14}/></button>}
            </>}
            {preview && !myRequest && <div className="retail-chat-preview"><strong>{exchangeAllowed ? "Initial checks passed" : "Not eligible for immediate proposal"}</strong><p>Policy: {preview.evidence_policy}</p>{preview.reasons.map((reason, i) => <p key={i}>{reason}</p>)}</div>}
            {exchangeAllowed && !myRequest && <div className="retail-chat-confirm"><label><input type="checkbox" checked={condition} onChange={e => setCondition(e.target.checked)}/> I confirm the item is unworn, unwashed and has its tags (subject to staff inspection).</label><label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/> I explicitly request this exchange and understand manager approval is required.</label><button type="button" className="retail-chat-action-btn" disabled={!!busy || !condition || !confirmed} onClick={() => void submitExchange()}>Confirm & send request <ArrowRight size={14}/></button></div>}
            {myRequest && <div className="retail-chat-request-status"><CheckCircle2 size={18}/><div><strong>Exchange request received</strong><p>Reference: {myRequest.id}</p><p>Status: {nice(status?.status || myRequest.status)}</p>{status?.record_reference && <p>Exchange record: {status.record_reference}</p>}<small>Not shipped. Pending applicable staff verification and manager approval.</small></div></div>}
            {lines.length === 0 && <p className="retail-chat-muted">Select a ticket associated with a purchased order, or create a new order-related support ticket.</p>}
          </div>}
          <button type="button" className="retail-chat-refresh" disabled={!!busy} onClick={() => void reload()}><RefreshCcw size={14}/> Refresh request status</button>
        </div>}
        {tab === "human" && <div className="retail-chat-scroll retail-chat-actions">
          <div className="retail-chat-panel-intro"><span>HUMAN SUPPORT</span><h3>Talk to our team.</h3><p>Create a ticket when an AI answer isn't sufficient. The request appears in the staff support inbox.</p></div>
          <label htmlFor="retail-help-order">Related order (optional)</label>
          <select id="retail-help-order" value={newTicketOrderId} onChange={e => setNewTicketOrderId(e.target.value)}><option value="">General question</option>{orders.map(o => <option key={o.id} value={o.id}>{o.id} — {o.items[0]?.product_title}</option>)}</select>
          <label htmlFor="retail-help-subject">Subject</label><input id="retail-help-subject" value={newSubject} onChange={e => setNewSubject(e.target.value)} maxLength={150} placeholder="What do you need help with?"/>
          <label htmlFor="retail-help-content">Describe your issue</label><textarea id="retail-help-content" rows={5} maxLength={6000} value={newMessage} onChange={e => setNewMessage(e.target.value)} placeholder="Tell us what happened…"/>
          <button type="button" className="retail-chat-action-btn" disabled={!!busy || !profile || newSubject.trim().length < 3 || newMessage.trim().length < 5} onClick={() => void createTicket()}><Headphones size={15}/> Create support ticket <ArrowRight size={14}/></button>
          <div className="retail-chat-human-note"><ShieldCheck size={15}/> Staff review is required for refunds, cancellations, and inventory-changing actions.</div>
        </div>}
        <footer className="retail-chat-drawer-footer"><ShoppingBag size={13}/> NORTHSTAR EDIT × NOVA · LOCAL SANDBOX</footer>
      </div>
    </>}
  </div>;
}

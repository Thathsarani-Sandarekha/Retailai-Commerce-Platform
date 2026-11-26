"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, ArrowDownRight, ArrowRight, BadgeCheck, Bot, Boxes, Check, CheckCheck, ChevronDown,
  ChevronRight, CircleAlert, CircleCheck, ClipboardList, Clock3, FileText, Headphones,
  Inbox, LayoutDashboard, LockKeyhole, MessageCircle, Package, PackageCheck, RefreshCcw,
  Search, Send, ShieldCheck, ShoppingBag, Sparkles, Truck, UserRound, WandSparkles, X,
} from "lucide-react";
import {
  api, type AgentResponse, type Analytics, type EvidenceContext, type ExchangeCheck,
  type ExchangeProposal, type ExchangeRecord, type Message, type Product, type Ticket, type Variant, type StaffSandboxOrder,
} from "@/lib/api";

type View = "workspace" | "approvals" | "orders";
const format = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (m) => m.toUpperCase());
const money = (cents: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
const time = (date: string) => new Date(date).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
const shortId = (id: string) => id.length > 18 ? `${id.slice(0, 8)}…` : id;

function Brand() {
  return <div className="brand-wrap">
    <div className="brand-mark"><span>N</span><span className="mark-slash" /></div>
    <div><div className="brand-name">northstar<span className="brand-dot">.</span></div><div className="brand-caption">NORTHSTAR EDIT · SERVICE DESK</div></div>
  </div>;
}
function Pill({ children, kind = "neutral" }: { children: React.ReactNode; kind?: "neutral" | "green" | "orange" | "blue" }) {
  return <span className={`pill pill-${kind}`}>{children}</span>;
}
function SectionTitle({ children, accessory }: { children: React.ReactNode; accessory?: React.ReactNode }) {
  return <div className="section-title"><h3>{children}</h3>{accessory}</div>;
}

export default function SupportConsole() {
  const [view, setView] = useState<View>("workspace");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [ticketId, setTicketId] = useState("N-T3");
  const [search, setSearch] = useState("");
  const [catalog, setCatalog] = useState<Product[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [context, setContext] = useState<EvidenceContext | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [proposals, setProposals] = useState<ExchangeProposal[]>([]);
  const [records, setRecords] = useState<ExchangeRecord[]>([]);
  const [agent, setAgent] = useState<AgentResponse | null>(null);
  const [healthMode, setHealthMode] = useState("checking");
  const [sandboxOrders, setSandboxOrders] = useState<StaffSandboxOrder[]>([]);
  const [question, setQuestion] = useState("Can this customer exchange medium leggings for a large?");
  const [conditionVerified, setConditionVerified] = useState(false);
  const [selectedLineId, setSelectedLineId] = useState("");
  const [selectedTargetId, setSelectedTargetId] = useState("");
  const [check, setCheck] = useState<ExchangeCheck | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(true);

  const selectedTicket = tickets.find((ticket) => ticket.id === ticketId);
  const ticketProposals = useMemo(() => proposals.filter((p) => p.ticket_id === ticketId), [proposals, ticketId]);
  const activeProposal = ticketProposals[0];
  const line = context?.line_items.find((x) => x.id === selectedLineId) || context?.line_items[0];
  const product = catalog.find((p) => p.id === line?.product_id);
  const availableTargets = product?.variants.filter((v) => v.id !== line?.variant_id) || [];
  const target = availableTargets.find((v) => v.id === selectedTargetId) || availableTargets.find((v) => v.size === "L") || availableTargets[0];
  const demoCustomerAllowed = selectedTicket?.customer_id === "N-C3";
  const inFlight = Boolean(busy);

  const refreshGlobal = useCallback(async () => {
    const [ticketData, catalogData, analyticsData, proposalData, healthData, checkoutData] = await Promise.all([
      api<Ticket[]>("/tickets"), api<Product[]>("/catalog"), api<Analytics>("/analytics/overview"),
      api<ExchangeProposal[]>("/exchange-proposals"), api<{ model_mode: string }>("/health"),
      api<StaffSandboxOrder[]>("/operations/sandbox-orders"),
    ]);
    setTickets(ticketData);
    setCatalog(catalogData);
    setAnalytics(analyticsData);
    setProposals(proposalData);
    setHealthMode(healthData.model_mode);
    setSandboxOrders(checkoutData);
  }, []);
  const refreshTicket = useCallback(async (id: string) => {
    const [details, history] = await Promise.all([
      api<EvidenceContext>(`/tickets/${id}/context`), api<Message[]>(`/tickets/${id}/messages`),
    ]);
    setContext(details);
    setMessages(history);
    if (details.order) setRecords(await api<ExchangeRecord[]>(`/orders/${details.order.id}/exchanges`));
    else setRecords([]);
  }, []);

  useEffect(() => { refreshGlobal().catch((e) => setError(e.message)); }, [refreshGlobal]);
  useEffect(() => {
    let current = true;
    setContext(null); setAgent(null); setCheck(null); setSelectedLineId(""); setSelectedTargetId(""); setConditionVerified(false);
    // The fetch is tied to the current ticket; ignore stale responses when switching rapidly.
    Promise.all([api<EvidenceContext>(`/tickets/${ticketId}/context`), api<Message[]>(`/tickets/${ticketId}/messages`)]).then(async ([d, m]) => {
      const rec = d.order ? await api<ExchangeRecord[]>(`/orders/${d.order.id}/exchanges`) : [];
      if (current) { setContext(d); setMessages(m); setRecords(rec); }
    }).catch((e) => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [ticketId]);

  const run = async (label: string, fn: () => Promise<string>) => {
    setBusy(label); setError(""); setNotice("");
    try { const message = await fn(); setNotice(message); await Promise.all([refreshGlobal(), refreshTicket(ticketId)]); }
    catch (e) { setError(e instanceof Error ? e.message : "Unexpected request failure"); }
    finally { setBusy(""); }
  };
  const askAgent = async () => {
    const q = question.trim(); if (q.length < 3) return;
    await run("assistant", async () => {
      const result = await api<AgentResponse>(`/tickets/${ticketId}/agent/chat`, { method: "POST", data: { message: q } });
      setAgent(result);
      setQuestion("");
      return "AI draft saved to ticket history. No customer message was sent.";
    });
  };
  const preview = async () => {
    if (!line || !target) return;
    await run("preview", async () => {
      const result = await api<ExchangeCheck>(`/tickets/${ticketId}/exchange-check`, {
        method: "POST", data: { order_line_id: line.id, target_variant_id: target.id, item_condition: conditionVerified ? "unworn_with_tags" : "unknown" },
      });
      setCheck(result);
      return result.eligible_for_proposal ? "Eligibility preview passed; no exchange has been created." : "Eligibility requires attention. Review the checklist below.";
    });
  };
  const propose = async () => {
    if (!line || !target || !conditionVerified || !check?.eligible_for_proposal) return;
    await run("propose", async () => {
      await api(`/tickets/${ticketId}/exchange-proposals`, { method: "POST", data: {
        order_line_id: line.id, target_variant_id: target.id, item_condition: "unworn_with_tags",
        reason: `Customer requested size ${line.size} to ${target.size} exchange; staff condition attested in demo`,
        idempotency_key: `ui-exchange-${ticketId}-${line.id}-${target.id}`,
      } });
      return "Exchange proposal created. Customer confirmation is still required.";
    });
  };
  const confirm = async () => {
    if (!activeProposal || !demoCustomerAllowed) return;
    await run("confirm", async () => {
      await api(`/exchange-proposals/${activeProposal.id}/customer-confirm`, { method: "POST", role: "customer-c3", data: {
        confirmed: true, target_variant_id: activeProposal.target_variant_id,
      } });
      return "Simulated synthetic customer N-C3 confirmed the selected size.";
    });
  };
  const staffVerify = async () => {
    if (!activeProposal) return;
    await run("verify-condition", async () => {
      await api(`/exchange-proposals/${activeProposal.id}/verify-condition`, {
        method: "POST", data: { verified_unworn_with_tags: true }, role: "staff",
      });
      return "Staff recorded physical-condition verification. Manager review is now required.";
    });
  };
  const approve = async () => {
    if (!activeProposal) return;
    await run("approve", async () => {
      await api(`/exchange-proposals/${activeProposal.id}/approve`, { method: "POST", role: "manager", data: {} });
      return "Demo manager approved the exchange; inventory is not reserved yet.";
    });
  };
  const execute = async () => {
    if (!activeProposal) return;
    await run("execute", async () => {
      await api(`/exchange-proposals/${activeProposal.id}/execute-local`, { method: "POST", role: "manager", data: {} });
      return "Authorized local transaction committed. Inventory and exchange record updated.";
    });
  };
  const changeTicket = (id: string) => { setTicketId(id); setNotice(""); setError(""); setView("workspace"); };
  const visibleTickets = tickets.filter((ticket) => `${ticket.id} ${ticket.subject} ${ticket.content}`.toLowerCase().includes(search.toLowerCase()));
  const totalTickets = Object.values(analytics?.tickets_by_status || {}).reduce((s, n) => s + n, 0);
  const pending = proposals.filter((p) => p.status === "pending_approval").length;
  const reserved = Object.values(analytics?.exchange_proposals_by_status || {}).reduce((s, n) => s + n, 0);

  return <div className="app-shell">
    <aside className="sidebar">
      <Brand />
      <div className="workspace-pill"><span className="workspace-avatar">N</span><div><strong>Northstar Store</strong><small>Demo workspace</small></div><ChevronDown size={15} /></div>
      <a href="/shop" className="nav-item" style={{color:"#aee1db", marginBottom:10, textDecoration:"none"}}><ShoppingBag size={17}/><span>Customer portal</span><ArrowRight size={15}/></a>
      <div className="sidebar-section-label">WORKSPACE</div>
      <nav className="navigation" aria-label="Primary">
        <button className={view === "workspace" ? "nav-item active" : "nav-item"} onClick={() => setView("workspace")}><Inbox size={18} /><span>Support inbox</span><span className="nav-count">{totalTickets}</span></button>
        <button className={view === "approvals" ? "nav-item active" : "nav-item"} onClick={() => setView("approvals")}><ClipboardList size={18} /><span>Exchange queue</span>{pending > 0 && <span className="nav-count attention">{pending}</span>}</button>
        <a href="/operations" className="nav-item" style={{textDecoration:"none"}}><LayoutDashboard size={18}/><span>Analytics overview</span><ArrowRight size={14}/></a>
      </nav>
      <div className="sidebar-section-label">PLATFORM</div>
      <div className="navigation"><button className={view === "orders" ? "nav-item active" : "nav-item"} onClick={() => setView("orders")}><Boxes size={18}/><span>Demo orders</span><span className="nav-count">{sandboxOrders.length}</span></button><div className="nav-item passive"><ShieldCheck size={18}/><span>Policy & security</span></div></div>
      <div className="sidebar-spacer" />
      <div className="model-card"><div className="model-card-title"><span className="online-dot" /> AI ENGINE ACTIVE</div><strong>Single-agent workflow</strong><p>Groq · LangGraph · Verified read tools</p><div className="model-mode">{healthMode === "checking" ? "Connecting…" : healthMode === "groq" ? "Groq connected" : `${format(healthMode)} mode`}</div></div>
      <div className="profile"><div className="profile-avatar">SA</div><div><strong>Support workspace</strong><small>Synthetic roles · local only</small></div><ChevronDown size={15}/></div>
    </aside>

    <div className="main-column">
      <header className="topbar"><div className="breadcrumbs">Workspace <ChevronRight size={14} /> <strong>{view === "workspace" ? "Support inbox" : view === "orders" ? "Demo orders" : "Exchange approvals"}</strong></div><div className="topbar-right"><span className="sandbox-tag"><span className="online-dot"/> SANDBOX ENVIRONMENT</span><div className="avatar-sm">NS</div></div></header>
      <main className="main-content">
        <div className="page-intro"><div><div className="eyebrow">CUSTOMER EXPERIENCE / OPERATIONS</div><h1>{view === "workspace" ? "Customer support" : view === "orders" ? "Sandbox orders" : "Exchange approvals"}<span className="title-period">.</span></h1><p>{view === "workspace" ? "Resolve customer requests with real order context and a tool-using AI copilot." : view === "orders" ? "See customer-confirmed synthetic orders created through the shared backend checkout service." : "Review explicit customer confirmations and authorize inventory reservations."}</p></div><button className="secondary-btn refresh" onClick={() => run("refresh", async () => "Business data refreshed.")} disabled={inFlight}><RefreshCcw size={16}/> Refresh</button></div>
        <div className="stat-row"><div className="stat-card"><div className="stat-icon blue"><Inbox size={19}/></div><div><span>Support tickets</span><strong>{totalTickets || "—"}</strong></div><ArrowDownRight className="stat-decoration" size={18}/></div><div className="stat-card"><div className="stat-icon violet"><Sparkles size={19}/></div><div><span>Exchange proposals</span><strong>{reserved}</strong></div></div><div className="stat-card"><div className="stat-icon peach"><Clock3 size={19}/></div><div><span>Awaiting manager</span><strong>{pending}</strong></div></div><div className="stat-card reliability"><div className="stat-icon green"><ShieldCheck size={19}/></div><div><span>Actions protected</span><strong>Approval gated</strong></div></div></div>
        {error && <div className="alert error" role="alert"><CircleAlert size={18}/><span>{error}</span><button onClick={() => setError("")} aria-label="Dismiss error"><X size={15}/></button></div>}
        {notice && <div className="alert notice" role="status"><CircleCheck size={18}/><span>{notice}</span><button onClick={() => setNotice("")} aria-label="Dismiss notification"><X size={15}/></button></div>}
        {view === "orders" ? <section className="approval-workbench" style={{maxWidth:1060, margin:"0 auto", width:"100%"}}>
          <div className="workbench-heading"><div><span className="overline">SHARED COMMERCE DATABASE / SANDBOX</span><h2>Customer-confirmed demo orders</h2><p>Real local order records and inventory updates. No payment, Shopify checkout or shipment.</p></div><PackageCheck size={26}/></div>
          <div style={{display:"flex", gap:14, flexWrap:"wrap", margin:"18px 0 26px"}}>
            <Pill kind="green">{sandboxOrders.length} local checkout(s)</Pill>
            <Pill kind="orange">Payment: not charged</Pill>
          </div>
          {sandboxOrders.length === 0 ? <p className="empty-state">No checkout orders yet. Create one from the customer portal and click Refresh.</p> :
           <div style={{display:"grid",gap:12}}>{sandboxOrders.map(order => <article className="shipment-card" key={order.reference} style={{padding:22,alignItems:"flex-start"}}>
             <div className="shipment-icon"><PackageCheck size={20}/></div><div style={{minWidth:0,flex:1}}>
               <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:8,flexWrap:"wrap"}}>
                 <strong>{order.order_id}</strong><strong>{money(order.total_cents)}</strong>
               </div>
               <p style={{margin:"9px 0"}}>Customer {order.customer_id} · {format(order.status)} · Payment not charged</p>
               <small>{order.items.map(item => `${item.product_title} (${item.size}, qty ${item.quantity})`).join(" · ")}</small>
               <p style={{margin:"8px 0 0",fontSize:11}}>Checkout reference: {order.reference}</p>
             </div></article>)}</div>}
          <button className="secondary-btn" style={{marginTop:22}} onClick={() => run("refresh", async () => "Order records refreshed.")}> <RefreshCcw size={15}/> Refresh orders</button>
        </section> : view === "workspace" ? <div className="workspace-grid">
          <section className="inbox-panel"><div className="panel-heading"><div><span className="overline">ALL CONVERSATIONS</span><h2>Inbox <span className="heading-count">{visibleTickets.length}</span></h2></div><span className="header-icon"><MessageCircle size={19}/></span></div><div className="search-wrap"><Search size={17}/><input aria-label="Search tickets" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search conversations..." /></div><div className="filter-strip"><span className="filter-pill selected">All tickets</span><span className="filter-pill">Open</span><span className="filter-pill">Pending</span></div><div className="ticket-list">{visibleTickets.map((ticket) => <button key={ticket.id} className={`ticket-item ${ticket.id === ticketId ? "selected" : ""}`} onClick={() => changeTicket(ticket.id)}><div className="ticket-item-head"><div className={`ticket-avatar ${ticket.id === "N-T3" ? "lavender" : ""}`}>{ticket.customer_id.replace("N-C", "C")}</div><span className="ticket-age">{ticket.id}</span></div><strong>{ticket.subject}</strong><p>{ticket.content}</p><div className="ticket-meta"><span className="mini-category">{format(ticket.intent === "unclassified" ? "Support" : ticket.intent)}</span><span className={`mini-status ${ticket.status === "exchange_processing" ? "done" : ""}`}><span/> {format(ticket.status)}</span></div></button>)}{!visibleTickets.length && <p className="empty-state">No tickets found.</p>}</div><div className="inbox-foot"><span className="online-dot"/> Data synced with local API</div></section>
          <section className="chat-panel"><div className="chat-header"><div className="chat-title-row"><div className="chat-customer-avatar"><UserRound size={22}/></div><div className="chat-customer-details"><div className="chat-main-title">{selectedTicket?.subject || "Loading conversation"}</div><div className="chat-subtitle">Customer {selectedTicket?.customer_id || "—"} <span>•</span> Order {selectedTicket?.order_id || "—"}</div></div></div><Pill kind={selectedTicket?.status === "exchange_processing" ? "green" : "orange"}>{format(selectedTicket?.status || "loading")}</Pill></div>
            <div className="chat-stream"><div className="thread-date">CUSTOMER CONVERSATION · SYNTHETIC DATA</div>{messages.map((msg) => <div key={msg.id} className={`message-row ${msg.delivery_status === "agent_draft" ? "ai-row" : msg.delivery_status === "agent_prompt" ? "prompt-row" : ""}`}><div className={`message-avatar ${msg.delivery_status === "agent_draft" ? "ai" : ""}`}>{msg.delivery_status === "agent_draft" ? <Bot size={17}/> : msg.sender === "customer" ? <UserRound size={16}/> : <Headphones size={16}/>}</div><div className="message-body"><div className="message-author">{msg.delivery_status === "agent_draft" ? "AI assistant" : msg.delivery_status === "agent_prompt" ? "Support agent · Prompt" : msg.delivery_status === "customer_ai_response" ? "AI assistant · Delivered to customer" : msg.sender === "customer" ? "Customer" : "Support draft"}<span>{time(msg.created_at)}</span></div><div className="message-bubble">{msg.body}</div>{msg.delivery_status === "agent_draft" && <span className="draft-only"><LockKeyhole size={12}/> Internal draft · not sent to customer</span>}</div></div>)}{!messages.length && <div className="empty-state">Loading messages…</div>}{agent && <div className="trace-panel"><div className="trace-heading"><Activity size={15}/> Latest agent tool trace <Pill kind="green">{agent.graph_engine}</Pill></div><div className="trace-items">{agent.tool_trace.map((t, i) => <span key={i}><CheckCheck size={13}/> {t.tool} <em>{t.status}</em></span>)}</div><div className="trace-foot">{agent.steps} reasoning/tool steps · transaction_executed: false</div></div>}</div>
            <div className="composer"><div className="composer-label"><WandSparkles size={16}/> ASK THE AI COPILOT <span>READ-ONLY TOOLS</span></div><textarea aria-label="Ask AI agent" rows={2} placeholder="Ask the AI to investigate this customer's request..." value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); void askAgent(); } }}/><div className="composer-footer"><span><LockKeyhole size={13}/> Drafts are never auto-sent</span><button className="primary-btn" onClick={askAgent} disabled={inFlight || question.trim().length < 3}><Send size={15}/>{busy === "assistant" ? "Thinking…" : "Generate draft"}</button></div></div>
          </section>
          <aside className="context-panel"><div className="context-header"><div><span className="overline">LIVE BUSINESS CONTEXT</span><h2>Order details</h2></div><button className="icon-button" onClick={() => setDetailsOpen((s) => !s)} aria-label="Toggle order details"><ChevronDown size={18}/></button></div>{detailsOpen && <><div className="context-order-banner"><div><span>LINKED ORDER</span><strong>{context?.order?.id || "—"}</strong></div><Pill kind="green">{format(context?.order?.fulfillment_status || "loading")}</Pill></div><div className="context-body"><div className="info-grid"><div><span>Customer</span><strong>{selectedTicket?.customer_id || "—"}</strong></div><div><span>Order value</span><strong>{context?.order ? money(context.order.total_cents) : "—"}</strong></div><div><span>Tracking</span><strong>{context?.order?.tracking_number || "—"}</strong></div><div><span>Delivery</span><strong>{context?.order?.delivered_at ? "Delivered" : "Not delivered"}</strong></div></div>
            <SectionTitle>Purchased items</SectionTitle>{context?.line_items.map((item) => <div key={item.id} className="product-row"><div className="product-thumb"><ShoppingBag size={25}/></div><div><strong>{item.product_title}</strong><small>Size {item.size} · {item.color} · Qty {item.quantity}</small></div></div>)}
            <SectionTitle accessory={<span className="tiny-muted">LIVE LOCAL STOCK</span>}>Available sizes</SectionTitle><div className="size-list">{product?.variants.map((v) => <div key={v.id} className={`size-chip ${v.id === target?.id ? "selected-size" : ""}`}><strong>{v.size}</strong><small>{v.available_quantity}</small></div>) || <span className="tiny-muted">Choose a ticket with a product to view sizes.</span>}</div>
            <SectionTitle>Shipping activity</SectionTitle>{context?.shipments.length ? context.shipments.map((sh) => <div key={sh.id} className="shipment-card"><div className="shipment-icon"><Truck size={18}/></div><div><strong>{format(sh.status)}</strong><small>{sh.carrier} · {sh.tracking_number}</small>{sh.events.at(-1) && <p>{sh.events.at(-1)?.description}</p>}</div></div>) : <p className="tiny-muted">No shipments linked.</p>}
            <SectionTitle accessory={<FileText size={15} />}>Policy evidence</SectionTitle>{context?.policies.slice(0,2).map((p) => <details className="policy-card" key={p.id}><summary><FileText size={16}/><span>{p.title.replace(" — synthetic", "")}</span><ChevronDown size={14}/></summary><p>{p.content}</p><small>{p.id}@{p.version}</small></details>)}
            <button className="outline-action" onClick={() => setView("approvals")}><PackageCheck size={17}/> Open exchange workflow <ArrowRight size={16}/></button>
          </div></>}</aside>
        </div> : <div className="approvals-layout"><section className="approval-workbench"><div className="workbench-heading"><div><span className="overline">CONTROLLED BUSINESS OPERATION</span><h2>Size exchange · {selectedTicket?.order_id || "N-1003"}</h2><p>Each stage is executed through a separate, authorized FastAPI operation. No LLM writes to inventory.</p></div><ShieldCheck size={27}/></div><div className="stepper"><span className="step-active">1. Verify</span><ArrowRight size={15}/><span>2. Confirm</span><ArrowRight size={15}/><span>3. Approve</span><ArrowRight size={15}/><span>4. Reserve</span></div><div className="form-group"><label htmlFor="exchange-ticket">Ticket</label><select id="exchange-ticket" value={ticketId} onChange={(e) => changeTicket(e.target.value)}>{tickets.map((t) => <option key={t.id} value={t.id}>{t.id} — {t.subject}</option>)}</select></div><div className="form-row"><div className="form-group"><label htmlFor="original-line">Purchased item</label><select id="original-line" value={line?.id || ""} onChange={(e) => { setSelectedLineId(e.target.value); setSelectedTargetId(""); setCheck(null); }}>{context?.line_items.map((l) => <option key={l.id} value={l.id}>{l.product_title} · {l.size}</option>)}</select></div><div className="form-group"><label htmlFor="replacement-variant">Replacement variant</label><select id="replacement-variant" value={target?.id || ""} onChange={(e) => { setSelectedTargetId(e.target.value); setCheck(null); }}>{availableTargets.map((v) => <option key={v.id} value={v.id}>Size {v.size} · {v.available_quantity} available</option>)}</select></div></div><label className="check-row"><input type="checkbox" checked={conditionVerified} onChange={(e) => { setConditionVerified(e.target.checked); setCheck(null); }} /><span><strong>Staff condition attestation (synthetic demo)</strong><small>I confirm that the item is unworn, unwashed and has original tags. No physical inspection is performed by this software.</small></span></label><button className="secondary-btn wide-button" onClick={preview} disabled={!line || !target || inFlight}><Search size={17}/>{busy === "preview" ? "Checking…" : "Run deterministic policy & stock check"}</button>{check && <div className={`eligibility-panel ${check.eligible_for_proposal ? "eligible" : "ineligible"}`}><strong>{check.eligible_for_proposal ? <CircleCheck size={18}/> : <CircleAlert size={18}/>} {check.eligible_for_proposal ? "Eligible to propose" : "Eligibility not established"}</strong><div className="check-grid">{Object.entries(check.checks).map(([name, ok]) => <div key={name}><span className={ok ? "checkmark good" : "checkmark bad"}>{ok ? <Check size={12}/> : <X size={12}/>}</span>{format(name)}</div>)}</div>{check.reasons.length > 0 && <p>{check.reasons.join(" • ")}</p>}<small>{check.evidence_policy} · {check.condition_source}</small></div>}
            <div className="actions-stack"><div className="action-step"><span className="action-number">01</span><div><strong>Create exchange proposal</strong><p>Stores target size and reason without changing stock.</p></div><button className="action-btn" onClick={propose} disabled={inFlight || Boolean(activeProposal) || !conditionVerified || !check?.eligible_for_proposal}>{activeProposal ? "Created" : "Propose"}</button></div><div className="action-step"><span className="action-number">02</span><div><strong>Customer confirmation</strong><p>Uses synthetic customer N-C3's distinct demo identity.</p></div><button className="action-btn" onClick={confirm} disabled={inFlight || !demoCustomerAllowed || activeProposal?.status !== "pending_customer_confirmation"}>{activeProposal?.status === "pending_customer_confirmation" ? "Simulate consent" : "Recorded / N/A"}</button></div><div className="action-step"><span className="action-number">03</span><div><strong>Manager authorization</strong><p>Independent approval is required before reservation.</p></div><button className="action-btn" onClick={approve} disabled={inFlight || activeProposal?.status !== "pending_approval"}>{activeProposal?.status === "pending_approval" ? "Approve" : "Locked / Done"}</button></div><div className="action-step"><span className="action-number">04</span><div><strong>Execute local reservation</strong><p>Atomic inventory decrement and durable exchange record.</p></div><button className="action-btn primary" onClick={execute} disabled={inFlight || activeProposal?.status !== "approved_not_executed"}>{activeProposal?.status === "approved_not_executed" ? "Reserve stock" : "Locked / Done"}</button></div></div>
            {activeProposal?.status === "pending_staff_review" &&
              <div className="eligibility-panel" style={{ marginTop: 20 }}>
                <strong>Customer submitted exchange · staff condition review required</strong>
                <p>Customer declared unworn condition, but staff must independently verify it. Only a support agent may record that verification.</p>
                <button className="action-btn primary" disabled={inFlight} onClick={staffVerify}>Verify unworn / tags checked</button>
              </div>}
          </section><aside className="approval-aside"><div className="approval-aside-card"><span className="overline">TRANSACTION STATUS</span><h3>{activeProposal ? format(activeProposal.status) : "No proposal yet"}</h3><p>{activeProposal ? `Proposal ${shortId(activeProposal.id)}` : "Create and validate an exchange proposal to begin."}</p><div className="approval-detail"><span>Linked ticket</span><strong>{ticketId}</strong></div><div className="approval-detail"><span>Replacement size</span><strong>{target?.size || "—"}</strong></div><div className="approval-detail"><span>Stock available now</span><strong>{target?.available_quantity ?? "—"} units</strong></div><div className="approval-detail"><span>Exchange records</span><strong>{records.length}</strong></div>{records.map((r) => <div key={r.id} className="record-card"><PackageCheck size={20}/><div><strong>{format(r.status)}</strong><small>Record {shortId(r.id)} · Qty {r.quantity}</small></div></div>)}</div><div className="aside-notice"><LockKeyhole size={20}/><div><strong>Local demo boundaries</strong><p>Demo roles are simulated, not production authentication. An exchange record means stock reserved pending return; no Shopify mutation or shipment occurs.</p></div></div><button className="secondary-btn wide-button" onClick={() => run("refresh", async () => "Updated local exchange state loaded.")} disabled={inFlight}><RefreshCcw size={15}/> Recheck business data</button></aside></div>}
      </main>
    </div>
  </div>;
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Image from "next/image";
import {
  Activity, ArrowRight, BarChart3, Boxes, CheckCircle2, ChevronDown,
  CreditCard, Headphones, LayoutDashboard, PackageCheck, RefreshCw,
  Search, ShieldCheck, ShoppingBag, Sparkles, TriangleAlert, TrendingUp,
} from "lucide-react";
import { api } from "@/lib/api";
import "./operations.css";
import "./premium-operations.css";

type Tab = "overview" | "inventory" | "orders" | "ai";
type Metrics = {
  total_tickets: number; open_tickets: number; resolved_tickets: number;
  escalated_tickets: number; pending_exchanges: number; reserved_exchanges: number;
  sandbox_orders: number; sandbox_order_value_cents: number;
  low_stock_variants: number; out_of_stock_variants: number;
  catalog_products: number; ai_responses: number; tool_calls: number; tool_failures: number;
};
type Inventory = {
  product_id: string; product_title: string; category: string; variant_id: string;
  sku: string; size: string; color: string; price_cents: number;
  available_quantity: number; level: "low" | "out" | "healthy";
};
type SandboxOrder = {
  reference: string; order_id: string; customer_id: string; total_cents: number;
  status: string; payment_status: "not_charged" | "simulated_paid"; created_at: string; item_count: number;
};
type ActivityRecord = { date: string; tickets: number; demo_orders: number };
type InsightData = {
  generated_at: string; environment: string; currency: "USD"; metrics: Metrics;
  payment_note: string; ticket_statuses: Record<string, number>;
  ticket_intents: Record<string, number>; daily_activity: ActivityRecord[];
  inventory: Inventory[]; recent_orders: SandboxOrder[];
  recent_tickets: { id: string; subject: string; status: string; intent: string; order_id: string | null; created_at: string }[];
  tool_summary: { tool: string; calls: number; ok: number; failed: number }[];
  recent_audit: { event: string; actor_id: string; resource_id: string; created_at: string }[];
  notes: string[];
};

const dollars = (cents: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
const format = (text: string) => text.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const date = (text: string) => new Date(text).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const datetime = (text: string) => new Date(text).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function StateTag({ status }: { status: string }) {
  const caution = /pending|review|open|low|awaiting|escalated/i.test(status);
  const negative = /out|failed|reject|error/i.test(status);
  return <span className={`ops-tag ${negative ? "ops-tag-negative" : caution ? "ops-tag-warn" : "ops-tag-ok"}`}>{format(status)}</span>;
}

function Panel({ title, eyebrow, children, right }: { title: string; eyebrow?: string; children: React.ReactNode; right?: React.ReactNode }) {
  return <section className="ops-panel"><div className="ops-panel-head"><div>{eyebrow && <span className="ops-eyebrow">{eyebrow}</span>}<h2>{title}</h2></div>{right}</div>{children}</section>;
}

function Empty({ message }: { message: string }) {
  return <div className="ops-empty"><Boxes size={24}/><p>{message}</p></div>;
}

export default function OperationsDashboard() {
  const [data, setData] = useState<InsightData | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [stockFilter, setStockFilter] = useState("all");
  const [opsGuideOpen, setOpsGuideOpen] = useState(false);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setData(await api<InsightData>("/operations/insights", { role: "staff" })); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load operational data"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const inventory = useMemo(() => (data?.inventory || []).filter((v) => {
    const match = `${v.product_title} ${v.category} ${v.sku} ${v.size} ${v.color}`.toLowerCase().includes(query.toLowerCase());
    return match && (stockFilter === "all" || v.level === stockFilter);
  }), [data, query, stockFilter]);
  const maxDay = Math.max(1, ...(data?.daily_activity.map((item) => Math.max(item.tickets, item.demo_orders)) || [1]));
  const maxIntent = Math.max(1, ...Object.values(data?.ticket_intents || {}));

  const nav: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: "overview", label: "Overview", icon: <LayoutDashboard size={17}/> },
    { key: "inventory", label: "Inventory", icon: <Boxes size={17}/> },
    { key: "orders", label: "Sandbox orders", icon: <ShoppingBag size={17}/> },
    { key: "ai", label: "AI monitoring", icon: <Activity size={17}/> },
  ];
  const metrics = data?.metrics;

  return <div className="ops-shell">
    <aside className="ops-sidebar">
      <div className="ops-identity"><div className="ops-mark">✦</div><div><strong>NORTHSTAR<span>®</span></strong><small>THE EDIT / OPERATIONS</small></div></div>
      <div className="ops-side-label">OPERATIONS WORKSPACE</div>
      <nav aria-label="Operations sections" className="ops-side-nav">{nav.map((item) => <button key={item.key} className={`ops-side-link ${tab === item.key ? "selected" : ""}`} onClick={() => setTab(item.key)}>{item.icon}<span>{item.label}</span>{tab === item.key && <ArrowRight size={13}/>}</button>)}</nav>
      <div className="ops-side-label ops-side-label-links">OTHER APPLICATIONS</div>
      <a className="ops-side-link" href="/operations/manage"><Boxes size={17}/> Manage catalog & tickets <ArrowRight size={14}/></a>
      <a className="ops-side-link" href="/"><Headphones size={17}/> Support inbox <ArrowRight size={14}/></a>
      <a className="ops-side-link" href="/shop"><ShoppingBag size={17}/> Customer store <ArrowRight size={14}/></a>
      <div className="ops-side-foot"><ShieldCheck size={17}/><div><strong>Local staff demo</strong><span>Synthetic records · No real charges</span></div></div>
    </aside>

    <main className="ops-main">
      <header className="ops-top"><div className="ops-breadcrumb">Workspace <span>/</span> Business intelligence <span>/</span> {nav.find((item) => item.key === tab)?.label}</div><div className="ops-env"><span className="ops-dot"/> SANDBOX DATA</div></header>
      <div className="ops-content">
        <div className="ops-title-row"><div><div className="ops-kicker">THE NORTHSTAR EDIT / OPERATIONS</div><h1>{tab === "overview" ? "Operations Dashboard" : tab === "inventory" ? "Inventory Control" : tab === "orders" ? "Order Operations" : "AI Performance"}</h1><p>{tab === "overview" ? "Real records from your synthetic customer and staff systems." : tab === "inventory" ? "Verified variant-level availability from the shared catalog." : tab === "orders" ? "Local checkouts created after customer confirmation. Payments are not processed." : "Observed agent tool calls, reply counts and sanitized audit events."}</p></div><button onClick={() => void load()} className="ops-refresh" disabled={loading}><RefreshCw size={15} className={loading ? "ops-spin" : ""}/>{loading ? "Refreshing" : "Refresh data"}</button></div>
        {error && <div role="alert" className="ops-alert"><TriangleAlert size={16}/> {error}. Verify that FastAPI and the local demo proxy are running.</div>}
        {loading && !data && <div className="ops-loading"><Sparkles size={22}/> Loading verified business records…</div>}
        {data && <>
          <div className="ops-source-row"><span><CheckCircle2 size={14}/> LIVE DATABASE AGGREGATION</span><span>Updated {datetime(data.generated_at)}</span></div>

          {tab === "overview" && <>
            <div className="ops-kpis">
              <div className="ops-kpi"><span><Headphones size={16}/> SUPPORT TICKETS</span><strong>{metrics?.total_tickets ?? 0}</strong><small>{metrics?.open_tickets ?? 0} active · {metrics?.resolved_tickets ?? 0} resolved</small></div>
              <div className="ops-kpi"><span><ShoppingBag size={16}/> DEMO CHECKOUTS</span><strong>{metrics?.sandbox_orders ?? 0}</strong><small>Customer-confirmed local orders</small></div>
              <div className="ops-kpi"><span><CreditCard size={16}/> UNPAID ORDER VALUE</span><strong>{dollars(metrics?.sandbox_order_value_cents ?? 0)}</strong><small>Not revenue · no payment charged</small></div>
              <div className="ops-kpi"><span><PackageCheck size={16}/> PENDING EXCHANGES</span><strong>{metrics?.pending_exchanges ?? 0}</strong><small>{metrics?.reserved_exchanges ?? 0} replacement reservations</small></div>
              <div className="ops-kpi"><span><TriangleAlert size={16}/> STOCK ALERTS</span><strong>{(metrics?.low_stock_variants ?? 0) + (metrics?.out_of_stock_variants ?? 0)}</strong><small>{metrics?.out_of_stock_variants ?? 0} out · {metrics?.low_stock_variants ?? 0} low</small></div>
              <div className="ops-kpi"><span><Activity size={16}/> AGENT TOOL CALLS</span><strong>{metrics?.tool_calls ?? 0}</strong><small>{metrics?.tool_failures ?? 0} recorded non-OK outcomes</small></div>
            </div>
            <div className="ops-two-up">
              <Panel title="Last 7 days" eyebrow="TICKET & CHECKOUT ACTIVITY" right={<div className="ops-legend"><span><i className="ops-legend-ticket"/> Tickets</span><span><i className="ops-legend-order"/> Orders</span></div>}>
                <div className="ops-activity-chart" role="img" aria-label="Seven-day chart of tickets created and demo orders placed"><div className="ops-chart-bars">{data.daily_activity.map((item) => <div className="ops-day" key={item.date}><div className="ops-bar-pair"><div title={`${item.tickets} tickets`} className="ops-bar ops-bar-ticket" style={{height: `${Math.max(0, item.tickets / maxDay * 100)}%`}}/><div title={`${item.demo_orders} demo orders`} className="ops-bar ops-bar-order" style={{height: `${Math.max(0, item.demo_orders / maxDay * 100)}%`}}/></div><span>{date(item.date)}</span></div>)}</div></div><p className="ops-panel-note">Dates are based on stored creation timestamps. No simulated growth is inserted.</p>
              </Panel>
              <Panel title="Why customers contact us" eyebrow="TICKET CLASSIFICATION"><div className="ops-intents">{Object.entries(data.ticket_intents).sort((a, b) => b[1] - a[1]).map(([intent, count]) => <div className="ops-intent-row" key={intent}><div><span>{format(intent)}</span><strong>{count}</strong></div><div className="ops-meter"><span style={{width:`${100 * count / maxIntent}%`}}/></div></div>)}{!Object.keys(data.ticket_intents).length && <Empty message="No tickets recorded."/>}</div><p className="ops-panel-note">Unclassified tickets remain unclassified until triage.</p></Panel>
            </div>
            <div className="edit-ops-action-grid">
              <Panel title="Support overview" eyebrow="LATEST CUSTOMER REQUESTS" right={<a className="ops-subtle-link" href="/">All tickets <ArrowRight size={14}/></a>}>
                <div className="ops-table-scroll"><table className="ops-table"><thead><tr><th>Ticket</th><th>Subject</th><th>Status</th></tr></thead><tbody>{data.recent_tickets.slice(0, 5).map(t => <tr key={t.id}><td className="ops-mono">{t.id}</td><td>{t.subject}</td><td><StateTag status={t.status}/></td></tr>)}</tbody></table>{!data.recent_tickets.length && <Empty message="No support tickets yet."/>}</div>
              </Panel>
              <Panel title="Pending approvals" eyebrow="ACTIONS REQUIRING REVIEW">
                <div className="edit-ops-approval-row"><div><CheckCircle2 size={17}/> Exchanges for review</div><strong>{metrics?.pending_exchanges ?? 0}</strong></div>
                <div className="edit-ops-approval-row"><div><PackageCheck size={17}/> Reserved replacements</div><strong>{metrics?.reserved_exchanges ?? 0}</strong></div>
                <div className="edit-ops-approval-row"><div><TriangleAlert size={17}/> Stock alerts</div><strong>{(metrics?.low_stock_variants ?? 0) + (metrics?.out_of_stock_variants ?? 0)}</strong></div>
                <a className="edit-ops-panel-action" href="/operations/manage">REVIEW APPROVALS <ArrowRight size={14}/></a>
              </Panel>
              <Panel title="Inventory alerts" eyebrow="VARIANTS NEEDING ATTENTION">
                <div className="edit-ops-stock-list">{data.inventory.filter(v => v.level !== "healthy").slice(0,4).map(v=><div key={v.variant_id}><span><strong>{v.product_title}</strong><small>{v.size} · {v.color} · {v.sku}</small></span><StateTag status={v.level === "out" ? "out of stock" : "low stock"}/></div>)}{!data.inventory.some(v => v.level !== "healthy") && <Empty message="No stock alerts right now."/>}</div>
                <button type="button" className="edit-ops-panel-action" onClick={() => {setTab("inventory");setStockFilter("low");}}>CHECK INVENTORY <ArrowRight size={14}/></button>
              </Panel>
            </div>
            <div className="ops-two-up edit-ops-bottom-row">
              <Panel title="Recent operations" eyebrow="APPROVALS & CHANGES"><div className="ops-audit-list">{data.recent_audit.slice(0,6).map((a,i)=><div className="ops-audit-row" key={`${a.event}-${a.created_at}-${i}`}><div className="ops-audit-dot"/><div><strong>{format(a.event)}</strong><small>{a.resource_id} · {datetime(a.created_at)}</small></div></div>)}{!data.recent_audit.length && <Empty message="No activity recorded yet."/>}</div></Panel>
              <div className="edit-ops-copilot"><div className="edit-ops-copilot-heading"><Sparkles size={19}/> NOVA <span>/ TEAM SHORTCUTS</span></div><div className="edit-ops-copilot-body"><Image src="/images/brand/northstar-bot.webp" width={120} height={120} alt="NOVA, the friendly operations guide"/><div><h3>Hi, team!</h3><p>Quick access to the tools your team already uses.</p></div></div><div className="edit-ops-copilot-shortcuts"><button type="button" onClick={() => setTab("inventory")}><Boxes size={15}/> Check stock</button><a href="/operations/manage"><CheckCircle2 size={15}/> Approvals</a><button type="button" onClick={() => setTab("orders")}><ShoppingBag size={15}/> Orders</button><a href="/"><Headphones size={15}/> Support</a><button type="button" onClick={() => setTab("ai")}><Activity size={15}/> AI activity</button></div></div>
            </div>
          </>}

          {tab === "inventory" && <Panel title="Live product variants" eyebrow={`${data.inventory.length} VARIANTS · ${metrics?.catalog_products ?? 0} PRODUCTS`} right={<StateTag status={`${(metrics?.low_stock_variants ?? 0) + (metrics?.out_of_stock_variants ?? 0)} stock alerts`}/>}>
            <div className="ops-controls"><label className="ops-search"><Search size={16}/><input placeholder="Search product, SKU, size, color…" value={query} onChange={(e) => setQuery(e.target.value)} /></label><label className="ops-filter">Stock level <ChevronDown size={13}/><select aria-label="Stock filter" value={stockFilter} onChange={(e) => setStockFilter(e.target.value)}><option value="all">All variants</option><option value="low">Low stock (1–5)</option><option value="out">Out of stock</option><option value="healthy">Healthy</option></select></label></div>
            <div className="ops-table-scroll"><table className="ops-table ops-inventory-table"><thead><tr><th>Product</th><th>Variant</th><th>SKU</th><th className="ops-right">Price</th><th className="ops-right">Available</th><th>Status</th></tr></thead><tbody>{inventory.map((v) => <tr key={v.variant_id}><td><strong>{v.product_title}</strong><small>{format(v.category)}</small></td><td>{v.color} · {v.size}</td><td className="ops-mono">{v.sku}</td><td className="ops-right">{dollars(v.price_cents)}</td><td className="ops-right ops-count">{v.available_quantity}</td><td><StateTag status={v.level === "out" ? "out of stock" : v.level === "low" ? "low stock" : "healthy"}/></td></tr>)}</tbody></table>{!inventory.length && <Empty message="No variants match these filters."/>}</div><p className="ops-panel-note">Read-only inventory view. Stock is modified only by authorized order or exchange services.</p>
          </Panel>}

          {tab === "orders" && <>
            <div className="ops-order-summary"><CreditCard size={24}/><div><strong>{dollars(metrics?.sandbox_order_value_cents ?? 0)} in synthetic demo orders</strong><p>{data.payment_note} The seeded historical orders are excluded from this total.</p></div></div>
            <Panel title="Customer-confirmed demo checkouts" eyebrow="ACTUAL SANDBOX RECEIPTS"><div className="ops-table-scroll"><table className="ops-table"><thead><tr><th>Order</th><th>Customer</th><th>Items</th><th>Total</th><th>Created</th><th>Payment</th></tr></thead><tbody>{data.recent_orders.map((r) => <tr key={r.reference}><td><strong>{r.order_id}</strong><small>{r.reference}</small></td><td>{r.customer_id}</td><td>{r.item_count}</td><td>{dollars(r.total_cents)}</td><td>{datetime(r.created_at)}</td><td><StateTag status={r.payment_status === "simulated_paid" ? "demo paid" : "not charged"}/></td></tr>)}</tbody></table>{!data.recent_orders.length && <Empty message="No confirmed sandbox checkouts yet. Place one from the customer storefront to populate this table."/>}</div></Panel>
          </>}

          {tab === "ai" && <>
            <div className="ops-ai-strip"><div><Sparkles size={20}/><strong>{metrics?.ai_responses ?? 0}</strong><span>Observed agent replies/drafts</span></div><div><Activity size={20}/><strong>{metrics?.tool_calls ?? 0}</strong><span>Tool invocation events</span></div><div><TriangleAlert size={20}/><strong>{metrics?.tool_failures ?? 0}</strong><span>Non-OK tool outcomes</span></div></div>
            <div className="ops-two-up"><Panel title="Tool execution summary" eyebrow="AUDIT-BASED TOOL COUNTS"><div className="ops-table-scroll"><table className="ops-table"><thead><tr><th>Tool</th><th>Calls</th><th>Successful</th><th>Failed</th></tr></thead><tbody>{data.tool_summary.map((r) => <tr key={r.tool}><td className="ops-mono">{r.tool}</td><td>{r.calls}</td><td>{r.ok}</td><td>{r.failed}</td></tr>)}</tbody></table>{!data.tool_summary.length && <Empty message="No tool invocations recorded. Ask the assistant a question first."/>}</div></Panel>
              <Panel title="Audit activity" eyebrow="SANITIZED EVENT HISTORY"><div className="ops-audit-list">{data.recent_audit.slice(0, 15).map((a, i) => <div className="ops-audit-row" key={`${a.event}-${a.created_at}-${i}`}><div className="ops-audit-dot"/><div><strong>{format(a.event)}</strong><small>{a.actor_id} · {datetime(a.created_at)}</small></div></div>)}{!data.recent_audit.length && <Empty message="No audit events recorded."/>}</div></Panel></div>
            <div className="ops-boundary"><ShieldCheck size={18}/><span>Counts are from audit records, not quality scores. Prompt contents, tool arguments and customer conversations are excluded from this dashboard.</span></div>
          </>}
          <footer className="ops-footer"><BarChart3 size={16}/> RetailAI local operations · Synthetic identities and data · No live Shopify, payments or external sales claims</footer>
        </>}
      </div>
    </main>
    {!opsGuideOpen && <button type="button" className="ns-ops-assistant-launcher" onClick={() => setOpsGuideOpen(true)} aria-expanded="false" aria-controls="ns-ops-guide" aria-label="Open NOVA operations guide"><Image src="/images/brand/northstar-bot.webp" alt="" width={84} height={84}/><span className="ns-ops-launcher-dot"/></button>}
    {opsGuideOpen && <aside id="ns-ops-guide" className="ns-ops-guide" aria-label="NOVA operations shortcuts">
      <header><div><Sparkles size={15}/><strong>NOVA / TEAM SHORTCUTS</strong></div><button type="button" onClick={() => setOpsGuideOpen(false)} aria-label="Close operations guide">×</button></header>
      <div className="ns-ops-guide-hero"><Image src="/images/brand/northstar-bot.webp" width={124} height={124} alt="NOVA robot mascot"/><div><strong>Hello, team!</strong><p>A little help getting around your workspace.</p></div></div>
      <div className="ns-ops-guide-actions">
        <button type="button" onClick={() => {setTab("inventory");setStockFilter("low");setOpsGuideOpen(false);}}><Boxes size={16}/> Review low stock <ArrowRight size={14}/></button>
        <button type="button" onClick={() => {setTab("orders");setOpsGuideOpen(false);}}><ShoppingBag size={16}/> Check orders <ArrowRight size={14}/></button>
        <a href="/operations/manage"><CheckCircle2 size={16}/> Approvals & products <ArrowRight size={14}/></a>
        <a href="/"><Headphones size={16}/> Support inbox <ArrowRight size={14}/></a>
        <button type="button" onClick={() => {setTab("ai");setOpsGuideOpen(false);}}><Activity size={16}/> AI performance <ArrowRight size={14}/></button>
      </div>
      <small>Quick navigation using existing staff workflows.</small>
    </aside>}
  </div>;
}

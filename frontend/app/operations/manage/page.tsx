"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft, ArrowRight, Boxes, CheckCircle2, ClipboardList, History,
  LockKeyhole, Package, RefreshCw, Search, ShieldCheck, TriangleAlert, ImagePlus,
} from "lucide-react";
import { api } from "@/lib/api";
import "./management.css";
import "./premium-management.css";

type VariantRow = {
  variant_id: string; product_id: string; product_title: string;
  description: string; exchangeable: boolean; category: string;
  sku: string; size: string; color: string;
  price_cents: number; available_quantity: number;
};
type WorkTicket = {
  id: string; subject: string; customer_id: string; order_id: string | null;
  status: string; intent: string; created_at: string;
  priority: "low" | "normal" | "high" | "urgent";
  assigned_to: string | null; version: number;
};
type Event = { event: string; actor_id: string; created_at: string };
type Tab = "catalog" | "tickets";
const money = (value: number) => `$${(value / 100).toFixed(2)}`;
const titleCase = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const availableStates = ["open", "in_progress", "escalated", "resolved"];

export default function RetailOperationsManagement() {
  const [tab, setTab] = useState<Tab>("catalog");
  const [products, setProducts] = useState<VariantRow[]>([]);
  const [tickets, setTickets] = useState<WorkTicket[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedVariant, setSelectedVariant] = useState<VariantRow | null>(null);
  const [stock, setStock] = useState(0);
  const [price, setPrice] = useState("");
  const [selectedProduct, setSelectedProduct] = useState<VariantRow | null>(null);
  const [productTitle, setProductTitle] = useState("");
  const [productDescription, setProductDescription] = useState("");
  const [exchangeable, setExchangeable] = useState(true);
  const [catalogImage, setCatalogImage] = useState<File | null>(null);
  const [catalogPreview, setCatalogPreview] = useState("");
  useEffect(() => () => { if (catalogPreview) URL.revokeObjectURL(catalogPreview); }, [catalogPreview]);
  const [ticket, setTicket] = useState<WorkTicket | null>(null);
  const [ticketStatus, setTicketStatus] = useState("open");
  const [ticketPriority, setTicketPriority] = useState<WorkTicket["priority"]>("normal");
  const [assignedTo, setAssignedTo] = useState("");
  const [events, setEvents] = useState<Event[]>([]);

  const reload = useCallback(async () => {
    setBusy(true); setError("");
    try {
      const [catalog, work] = await Promise.all([
        api<VariantRow[]>("/operations/manage/inventory", { role: "staff" }),
        api<WorkTicket[]>("/operations/manage/tickets", { role: "staff" }),
      ]);
      setProducts(catalog); setTickets(work);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load business records"); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);

  const visibleProducts = useMemo(() => products.filter((r) =>
    `${r.product_title} ${r.sku} ${r.category} ${r.color} ${r.size}`.toLowerCase().includes(query.toLowerCase())), [products, query]);
  const visibleTickets = useMemo(() => tickets.filter((r) =>
    `${r.id} ${r.subject} ${r.status} ${r.intent} ${r.customer_id}`.toLowerCase().includes(query.toLowerCase())), [tickets, query]);
  const alertCount = products.filter((p) => p.available_quantity <= 5).length;

  function editVariant(v: VariantRow) {
    setSelectedProduct(null); setTicket(null); setSelectedVariant(v);
    setStock(v.available_quantity); setPrice((v.price_cents / 100).toFixed(2));
    setNotice(""); setError("");
  }
  function editProduct(v: VariantRow) {
    setSelectedVariant(null); setTicket(null); setSelectedProduct(v);
    setProductTitle(v.product_title); setProductDescription(v.description);
    setExchangeable(v.exchangeable); setCatalogImage(null); setCatalogPreview(""); setNotice(""); setError("");
  }
  function editTicket(t: WorkTicket) {
    setSelectedProduct(null); setSelectedVariant(null); setTicket(t);
    setTicketStatus(t.status); setTicketPriority(t.priority);
    setAssignedTo(t.assigned_to || ""); setEvents([]);
    setNotice(""); setError("");
    void api<Event[]>(`/operations/manage/tickets/${t.id}/activity`, { role: "staff" })
      .then(setEvents).catch(() => setEvents([]));
  }
  async function runSave(action: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); await reload(); }
    catch (e) { setError(e instanceof Error ? e.message : "Update failed"); }
    finally { setBusy(false); }
  }
  function saveVariant() {
    if (!selectedVariant) return;
    const current = selectedVariant;
    const entered = Number(price);
    if (!Number.isFinite(entered) || entered <= 0 || Math.abs(entered * 100 - Math.round(entered * 100)) > 0.00001 || stock < 0 || !Number.isInteger(stock)) {
      setError("Enter a valid positive price and non-negative quantity."); return;
    }
    void runSave(async () => {
      await api(`/operations/manage/variants/${current.variant_id}`, {
        method: "PATCH", role: "manager", data: {
          expected_available_quantity: current.available_quantity,
          new_available_quantity: stock,
          expected_price_cents: current.price_cents,
          new_price_cents: Math.round(entered * 100),
          reason: "Verified synthetic inventory/price adjustment",
        },
      });
      setSelectedVariant(null);
      setNotice(`Saved ${current.sku}; customer-facing prices and stock now use the new values.`);
    });
  }
  function saveProduct() {
    if (!selectedProduct) return;
    const current = selectedProduct;
    void runSave(async () => {
      await api(`/operations/manage/products/${current.product_id}`, {
        method: "PATCH", role: "manager", data: {
          expected_title: current.product_title,
          expected_description: current.description,
          expected_exchangeable: current.exchangeable, title: productTitle,
          description: productDescription, exchangeable,
          reason: "Verified synthetic catalog metadata correction",
        },
      });
      setSelectedProduct(null); setNotice("Product details updated in the shared catalog.");
    });
  }
  async function uploadCatalogImage() {
    if (!selectedProduct || !catalogImage) { setError("Choose a product image first."); return; }
    if (!["image/jpeg", "image/png", "image/webp"].includes(catalogImage.type) || catalogImage.size > 4 * 1024 * 1024 || !catalogImage.size) {
      setError("Choose a JPEG, PNG or WebP photo under 4 MB."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const form = new FormData(); form.append("image", catalogImage);
      const base = `/api/demo/integrations/storage/products/${encodeURIComponent(selectedProduct.product_id)}/image`;
      const result = await fetch(base, { method: "POST", headers: { "x-demo-role": "manager" }, body: form });
      if (!result.ok) { const problem = await result.json(); throw new Error(problem.detail || "Image upload failed"); }
      const preview = await fetch(base, { headers: { "x-demo-role": "manager" }, cache: "no-store" });
      if (!preview.ok) throw new Error("Uploaded image saved, but preview could not be retrieved");
      setCatalogPreview(URL.createObjectURL(await preview.blob()));
      setCatalogImage(null);
      setNotice("Product photo saved to the configured private image store.");
    } catch (e) { setError(e instanceof Error ? e.message : "Image upload failed"); }
    finally { setBusy(false); }
  }
  async function loadCatalogImage() {
    if (!selectedProduct) return;
    setBusy(true); setError("");
    try {
      const resp = await fetch(`/api/demo/integrations/storage/products/${encodeURIComponent(selectedProduct.product_id)}/image`,
        { headers: { "x-demo-role": "manager" }, cache: "no-store" });
      if (resp.status === 404) { setNotice("No custom photo uploaded for this product yet."); return; }
      if (!resp.ok) throw new Error("Could not retrieve the product image");
      setCatalogPreview(URL.createObjectURL(await resp.blob()));
    } catch (e) { setError(e instanceof Error ? e.message : "Image preview failed"); }
    finally { setBusy(false); }
  }
  function saveTicket() {
    if (!ticket) return;
    const current = ticket;
    void runSave(async () => {
      const updated = await api<WorkTicket>(`/operations/manage/tickets/${current.id}`, {
        method: "PATCH", role: "staff", data: {
          expected_status: current.status, expected_version: current.version,
          status: ticketStatus, priority: ticketPriority,
          assigned_to: assignedTo || null,
        },
      });
      setTicket(updated); setNotice(`Ticket ${updated.id} updated. All changes are logged.`);
      const activity = await api<Event[]>(`/operations/manage/tickets/${current.id}/activity`, { role: "staff" });
      setEvents(activity);
    });
  }

  return <div className="mg-shell">
    <aside className="mg-side">
      <div className="mg-brand"><span>R</span><div>RetailAI<strong>OPERATIONS STUDIO</strong></div></div>
      <a href="/operations"><ArrowLeft size={16}/> Analytics overview</a>
      <button className={tab === "catalog" ? "selected" : ""} onClick={() => { setTab("catalog"); setQuery(""); setTicket(null); }}><Boxes size={17}/> Catalog & inventory</button>
      <button className={tab === "tickets" ? "selected" : ""} onClick={() => { setTab("tickets"); setQuery(""); setSelectedVariant(null); setSelectedProduct(null); }}><ClipboardList size={17}/> Ticket operations</button>
      <a href="/"><ArrowRight size={16}/> Support console</a>
      <a href="/shop"><ArrowRight size={16}/> Customer storefront</a>
      <div className="mg-aside-foot"><ShieldCheck size={18}/> Local synthetic sandbox<br/>No Shopify write access</div>
    </aside>
    <main className="mg-main">
      <header className="mg-top"><span>WORKSPACE / RETAIL OPERATIONS / {tab === "catalog" ? "CATALOG" : "SUPPORT"}</span><span className="mg-sandbox">● SANDBOX ENVIRONMENT</span></header>
      <div className="mg-content">
        <div className="mg-heading"><div><p>RETAIL OPERATIONS / MANAGE</p><h1>{tab === "catalog" ? "Catalog & inventory control." : "Support ticket operations."}</h1><span>{tab === "catalog" ? "Manage verified product data with audited manager-only changes." : "Assign staff, prioritize issues and track safe ticket status transitions."}</span></div><button disabled={busy} onClick={() => void reload()}><RefreshCw size={16}/> Refresh data</button></div>
        <div className="mg-summary">
          <div><Package size={17}/><strong>{new Set(products.map((p) => p.product_id)).size}</strong><span>Catalog products</span></div>
          <div><Boxes size={17}/><strong>{products.length}</strong><span>Tracked variants</span></div>
          <div><TriangleAlert size={17}/><strong>{alertCount}</strong><span>Low / out-of-stock</span></div>
          <div><ClipboardList size={17}/><strong>{tickets.filter((t) => !["closed", "resolved"].includes(t.status)).length}</strong><span>Active tickets</span></div>
        </div>
        {error && <div role="alert" className="mg-alert"><TriangleAlert size={16}/> {error} — refresh the page if values have changed.</div>}
        {notice && <div role="status" className="mg-success"><CheckCircle2 size={16}/> {notice}</div>}
        <section className="mg-panel">
          <div className="mg-panel-head"><div><small>{tab === "catalog" ? "SHARED CATALOG" : "SHARED SUPPORT BACKEND"}</small><h2>{tab === "catalog" ? "All product variants" : "Customer support tickets"}</h2></div><label className="mg-search"><Search size={15}/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={tab === "catalog" ? "Search products, categories, SKU..." : "Search tickets, customer, status..."}/></label></div>
          <div className="mg-scroll"><table className="mg-table"><thead>{tab === "catalog" ? <tr><th>Product</th><th>Variant / SKU</th><th>Price</th><th>Stock</th><th>Actions</th></tr> : <tr><th>Ticket</th><th>Status</th><th>Priority</th><th>Assigned</th><th>Action</th></tr>}</thead><tbody>
            {tab === "catalog" ? visibleProducts.map((v) => <tr key={v.variant_id}><td><strong>{v.product_title}</strong><small>{titleCase(v.category)}</small></td><td>{v.color} · {v.size}<small>{v.sku}</small></td><td>{money(v.price_cents)}</td><td><span className={`mg-pill ${v.available_quantity === 0 ? "red" : v.available_quantity <= 5 ? "amber" : "green"}`}>{v.available_quantity} available</span></td><td><div className="mg-actions"><button onClick={() => editVariant(v)}>Adjust</button><button onClick={() => editProduct(v)}>Details</button></div></td></tr>) : visibleTickets.map((t) => <tr key={t.id}><td><strong>{t.subject}</strong><small>{t.id} · {t.customer_id} · {titleCase(t.intent)}</small></td><td><span className="mg-pill amber">{titleCase(t.status)}</span></td><td>{titleCase(t.priority)}</td><td>{t.assigned_to || "Unassigned"}</td><td><button className="mg-edit" onClick={() => editTicket(t)}>Manage <ArrowRight size={13}/></button></td></tr>)}
          </tbody></table>{(tab === "catalog" ? visibleProducts.length : visibleTickets.length) === 0 && <p className="mg-empty">No matching records found.</p>}</div>
        </section>
        <div className="mg-footnote"><LockKeyhole size={15}/> This is a role-simulation sandbox. Manager-only edits use a distinct demo credential; a public deployment requires real authentication and authorization.</div>
      </div>
    </main>
    {(selectedVariant || selectedProduct || ticket) && <div className="mg-modal-wrap" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) { setSelectedVariant(null); setSelectedProduct(null); setTicket(null); } }}><section className="mg-modal" role="dialog" aria-modal="true" aria-label="Manage retail record">
      <div className="mg-modal-heading"><div><small>{selectedVariant ? "MANAGER ONLY · AUDITED STOCK CHANGE" : selectedProduct ? "MANAGER ONLY · PRODUCT DETAILS" : "SUPPORT STAFF · TICKET ACTION"}</small><h2>{selectedVariant?.product_title || selectedProduct?.product_title || ticket?.subject}</h2></div><button onClick={() => { setSelectedVariant(null); setSelectedProduct(null); setTicket(null); }}>✕</button></div>
      {error && <div role="alert" className="mg-alert">{error}</div>}
      {notice && <div role="status" className="mg-success">{notice}</div>}
      {selectedVariant && <div className="mg-form"><p>{selectedVariant.color} · {selectedVariant.size} · {selectedVariant.sku}</p><label>Available quantity<input type="number" min={0} max={1000000} value={stock} onChange={(e) => setStock(Number(e.target.value))}/></label><label>Unit price (USD)<input inputMode="decimal" type="number" min="0.01" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)}/></label><div className="mg-help">Stock and prices are checked against the last values loaded. Customer checkout and styling tools use the updated database records.</div><button className="mg-primary" onClick={saveVariant} disabled={busy}>Save manager adjustment</button></div>}
      {selectedProduct && <div className="mg-form"><label>Product title<input value={productTitle} onChange={(e) => setProductTitle(e.target.value)}/></label><label>Product description<textarea value={productDescription} onChange={(e) => setProductDescription(e.target.value)} rows={4}/></label><label className="mg-check"><input type="checkbox" checked={exchangeable} onChange={(e) => setExchangeable(e.target.checked)}/> Product is exchangeable</label><div className="mg-help">Changes apply to the shared synthetic catalog. No live Shopify writes.</div><button className="mg-primary" onClick={saveProduct} disabled={busy}>Save product details</button>
      <div className="mg-upload-panel"><strong><ImagePlus size={16}/> Private catalog photo</strong><p>Manager-only upload · JPEG, PNG or WebP · 4 MB max · local or S3 storage.</p>
        <input aria-label="Select catalog product image" type="file" accept="image/jpeg,image/png,image/webp" onChange={e => setCatalogImage(e.target.files?.[0] || null)}/>
        <div className="mg-actions"><button disabled={busy || !catalogImage} onClick={() => void uploadCatalogImage()}>Upload image</button><button disabled={busy} onClick={() => void loadCatalogImage()}>View saved photo</button></div>
        {catalogPreview && <img className="mg-upload-preview" src={catalogPreview} alt="Stored catalog product photo preview"/>}
      </div></div>}
      {ticket && <div className="mg-form"><p>{ticket.id} · Customer {ticket.customer_id} {ticket.order_id && `· Order ${ticket.order_id}`}</p><label>Status<select value={ticketStatus} onChange={(e) => setTicketStatus(e.target.value)}>{[...new Set([ticket.status, ...availableStates])].map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}</select></label><label>Priority<select value={ticketPriority} onChange={(e) => setTicketPriority(e.target.value as WorkTicket["priority"])}>{["low", "normal", "high", "urgent"].map((v) => <option key={v} value={v}>{titleCase(v)}</option>)}</select></label><label>Assigned to<select value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)}><option value="">Unassigned</option><option value="northstar-agent-1">Northstar support agent</option><option value="northstar-manager-1">Northstar manager</option></select></label><button className="mg-primary" onClick={saveTicket} disabled={busy}>Save ticket updates</button><div className="mg-history"><h3><History size={15}/> Recorded activity</h3>{events.length ? events.map((ev, i) => <div key={`${ev.created_at}-${i}`}><strong>{titleCase(ev.event)}</strong><small>{ev.actor_id} · {new Date(ev.created_at).toLocaleString()}</small></div>) : <p>No ticket-level events recorded yet.</p>}</div></div>}
    </section></div>}
  </div>;
}

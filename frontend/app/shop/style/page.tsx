"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Check, CircleDollarSign, Heart, ShoppingBag, Sparkles, ShieldCheck, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import ProductPhoto from "@/components/ProductPhoto";
import "./style.css";

type Occasion = "casual" | "office" | "evening";
type OutfitItem = {
  product_id: string; variant_id: string; title: string; role: string;
  category: string; size: string; color: string; price_cents: number;
  available_quantity: number; style_score: number;
};
type OutfitResult = {
  feasible: boolean; occasion: Occasion; currency: "USD"; budget_cents: number;
  subtotal_cents: number; remaining_cents: number; minimum_complete_cents: number | null;
  shortfall_cents: number | null; items: OutfitItem[]; message: string;
  source: "synthetic_catalog"; cart_updated: false;
};
const usd = (cents: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
const occasions: { id: Occasion; name: string; subtitle: string; icon: string }[] = [
  { id: "casual", name: "Everyday Casual", subtitle: "Relaxed and effortless", icon: "01" },
  { id: "office", name: "Office Ready", subtitle: "Clean, confident layers", icon: "02" },
  { id: "evening", name: "Evening Out", subtitle: "A little extra polish", icon: "03" },
];
export default function StyleLabPage() {
  const [occasion, setOccasion] = useState<Occasion>("evening");
  const [budget, setBudget] = useState("220");
  const [clothingSize, setClothingSize] = useState("M");
  const [shoeSize, setShoeSize] = useState("US 8");
  const [denimSize, setDenimSize] = useState("28");
  const [result, setResult] = useState<OutfitResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [cartBusy, setCartBusy] = useState<string | null>(null);
  const [added, setAdded] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function generate() {
    const dollars = Number(budget);
    if (!Number.isFinite(dollars) || dollars < 10 || dollars > 10000) {
      setError("Enter a budget from $10 to $10,000."); return;
    }
    setBusy(true); setError(""); setNotice(""); setResult(null); setAdded([]);
    try {
      const outfit = await api<OutfitResult>("/customer/style/budget", {
        method: "POST", role: "customer-c3",
        data: { occasion, budget_cents: Math.round(dollars * 100),
          clothing_size: clothingSize, shoe_size: shoeSize, denim_size: denimSize },
      });
      setResult(outfit);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not prepare an outfit."); }
    finally { setBusy(false); }
  }

  async function addItem(item: OutfitItem) {
    setCartBusy(item.variant_id); setError(""); setNotice("");
    try {
      // Clicking the item-specific button explicitly confirms adding one unit.
      // The existing cart API rechecks current stock, permissions, and totals.
      await api("/customer/cart/items", { method: "POST", role: "customer-c3",
        data: { variant_id: item.variant_id, quantity: 1,
          idempotency_key: `style-${crypto.randomUUID()}` },
      });
      setAdded(previous => [...previous, item.variant_id]);
      setNotice(`${item.title} was added to your cart. No order or payment was created.`);
      window.dispatchEvent(new Event("retailai:cart-updated"));
    } catch (e) { setError(e instanceof Error ? e.message : "Could not add this item. Stock may have changed."); }
    finally { setCartBusy(null); }
  }

  return <div className="stylelab">
    <div className="stylelab-ribbon"><ShieldCheck size={13}/> SYNTHETIC RETAILAI DEMO · REAL DATABASE PRICE CHECKS · NO LIVE PAYMENT</div>
    <header className="stylelab-header">
      <Link className="stylelab-back" href="/shop"><ArrowLeft size={17}/> Back to the store</Link>
      <Link className="stylelab-brand" href="/shop">northstar<span>.</span><small>RETAILAI STYLE STUDIO</small></Link>
      <button className="stylelab-chat" onClick={() => window.dispatchEvent(new CustomEvent("retailai:open-assistant"))} type="button"><Sparkles size={16}/> Ask RetailAI</button>
    </header>
    <main className="stylelab-shell">
      <section className="stylelab-hero">
        <div>
          <div className="stylelab-eyebrow"><Sparkles size={15}/> RETAILAI / STYLE STUDIO / 01</div>
          <h1>Great style.<br/><em>Your budget.</em></h1>
          <p>Build a complete, shoppable look for your occasion using in-stock items and real catalog prices. No guesses. No surprise totals.</p>
          <div className="stylelab-hero-meta"><span><Check size={16}/> Budget-checked outfits</span><span><Check size={16}/> Live demo inventory</span></div>
        </div>
        <div className="stylelab-hero-art" aria-hidden="true"><div className="stylelab-orbit stylelab-orbit-one"/><div className="stylelab-orbit stylelab-orbit-two"/><span>R<span> / </span>A</span><small>YOUR STYLE, YOUR RULES</small></div>
      </section>
      <div className="three-looks-nav"><div><strong>Want to style one item three ways?</strong><span>Reuse your favorite jeans, skirt, dress, or blouse across three outfits.</span></div><Link href="/shop/style/three-looks">TRY THREE LOOKS <ArrowRight size={15}/></Link></div>
      <div className="three-looks-nav"><div><strong>Want to style an item you already own?</strong><span>Upload a photo and get shoppable outfit suggestions. Your garment is never added to the cart.</span></div><Link href="/shop/style/rescue">STYLE RESCUE STUDIO <ArrowRight size={15}/></Link></div>
      <section className="stylelab-workspace">
        <div className="stylelab-form">
          <div className="stylelab-sectiontop"><div className="stylelab-number">01</div><div><h2>Make it yours</h2><p>Tell us your occasion and sizes.</p></div></div>
          <label className="stylelab-label">Choose an occasion</label>
          <div className="stylelab-occasions">{occasions.map(o => <button type="button" key={o.id} className={occasion === o.id ? "stylelab-occasion selected" : "stylelab-occasion"} onClick={() => {setOccasion(o.id); setResult(null);}} aria-pressed={occasion === o.id}>
            <span>{o.icon}</span><strong>{o.name}</strong><small>{o.subtitle}</small>
          </button>)}</div>
          <label className="stylelab-label" htmlFor="stylelab-budget">Your total outfit budget (USD)</label>
          <div className="stylelab-budgetfield"><span>$</span><input id="stylelab-budget" inputMode="decimal" type="number" min="10" max="10000" step="1" value={budget} onChange={e => {setBudget(e.target.value); setResult(null);}}/><CircleDollarSign size={24}/></div>
          <div className="stylelab-quickbudgets">{[150, 200, 250, 300].map(amount => <button type="button" key={amount} onClick={() => {setBudget(String(amount)); setResult(null);}}>${amount}</button>)}</div>
          <div className="stylelab-sizes">
            <label>Clothing size<select value={clothingSize} onChange={e => setClothingSize(e.target.value)}>{["XS","S","M","L","XL"].map(s => <option key={s}>{s}</option>)}</select></label>
            <label>Shoe size<select value={shoeSize} onChange={e => setShoeSize(e.target.value)}>{["US 7","US 8","US 9"].map(s => <option key={s}>{s}</option>)}</select></label>
            <label>Denim waist<select value={denimSize} onChange={e => setDenimSize(e.target.value)}>{["26","28","30","32"].map(s => <option key={s}>{s}</option>)}</select></label>
          </div>
          <button className="stylelab-generate" type="button" disabled={busy} onClick={() => void generate()}><Sparkles size={18}/>{busy ? "Building your look..." : "Build my outfit"}<ArrowRight size={17}/></button>
          <p className="stylelab-disclaimer">Recommendations are curated-rule based and use the synthetic catalog. Generated looks do not reserve stock or create orders.</p>
        </div>
        <div className="stylelab-results" aria-live="polite">
          <div className="stylelab-sectiontop"><div className="stylelab-number">02</div><div><h2>Your curated look</h2><p>Selections are checked against your budget and inventory.</p></div></div>
          {!result && <div className="stylelab-empty"><div><Heart size={35}/></div><h3>Your new look starts here.</h3><p>Pick an occasion, set your budget, and create a complete outfit from our catalog.</p><span>NO OUTFIT GENERATED YET</span></div>}
          {result && !result.feasible && <div className="stylelab-notfit"><RotateCcw size={26}/><h3>Not quite within reach</h3><p>{result.message}</p>{result.minimum_complete_cents !== null && <p>Lowest available complete look: <strong>{usd(result.minimum_complete_cents)}</strong>. Increase your budget by at least <strong>{usd(result.shortfall_cents || 0)}</strong> or try another occasion.</p>}</div>}
          {result?.feasible && <>
            <div className="stylelab-summary"><div><span>{result.occasion.toUpperCase()} · VERIFIED OUTFIT</span><h3>{result.items.length} coordinated pieces</h3><p>Prices and available variants from Northstar&apos;s synthetic catalog</p></div><div className="stylelab-summarytotal"><span>TOTAL LOOK</span><strong>{usd(result.subtotal_cents)}</strong><small>{usd(result.remaining_cents)} under budget</small></div></div>
            <div className="stylelab-items">{result.items.map((item, index) => <div className="stylelab-item" key={item.variant_id}>
              <div className={`stylelab-item-art tone-${index % 4}`}><ProductPhoto productId={item.product_id} title={item.title}/><span className="stylelab-art-label">{item.role.toUpperCase()}</span></div>
              <div className="stylelab-item-details"><span>{item.category.toUpperCase()} / {item.color.toUpperCase()}</span><h4>{item.title}</h4><p>Size {item.size} · {item.available_quantity} available</p><button type="button" onClick={() => void addItem(item)} disabled={cartBusy !== null || added.includes(item.variant_id)}><ShoppingBag size={14}/>{added.includes(item.variant_id) ? "Added to cart" : cartBusy === item.variant_id ? "Adding..." : "Add this item"}</button></div>
              <strong className="stylelab-item-price">{usd(item.price_cents)}</strong>
            </div>)}</div>
            <div className="stylelab-bottomnote"><ShieldCheck size={15}/> Each item is added only after you click its button. Cart additions are revalidated by the backend.</div>
          </>}
          {error && <div role="alert" className="stylelab-error">{error}</div>}
          {notice && <div role="status" className="stylelab-notice">{notice}</div>}
        </div>
      </section>
    </main>
  </div>;
}

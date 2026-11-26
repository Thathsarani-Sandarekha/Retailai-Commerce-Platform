"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Check, Sparkles, ShieldCheck, ShoppingBag, Layers3 } from "lucide-react";
import { api } from "@/lib/api";
import ProductPhoto from "@/components/ProductPhoto";
import "../style.css";
import "./three-looks.css";

type AnchorVariant = {variant_id: string; size: string; color: string; price_cents: number; available_quantity: number};
type Anchor = {product_id: string; title: string; category: string; variants: AnchorVariant[]};
type LookItem = {product_id: string; variant_id: string; title: string; category: string; size: string; color: string; role: string; price_cents: number; available_quantity: number; already_owned: boolean};
type Look = {occasion: "casual" | "office" | "evening"; feasible: boolean; items: LookItem[]; outfit_value_cents: number | null; to_buy_cents: number | null; remaining_cents: number | null; shortfall_cents: number | null; missing_roles: string[]; message: string};
type ThreeLooksResult = {feasible: boolean; anchor?: LookItem; already_owned?: boolean; currency?: string; budget_cents?: number; looks: Look[]; message: string; cart_updated: false};
const usd = (cents: number) => new Intl.NumberFormat("en-US", {style:"currency", currency:"USD"}).format(cents / 100);
const OCCASIONS: {id: Look["occasion"]; title: string; label: string}[] = [
  {id: "casual", title: "01 / Weekend casual", label: "Easygoing staples"},
  {id: "office", title: "02 / Office ready", label: "Polished daily layers"},
  {id: "evening", title: "03 / Evening out", label: "A more elevated finish"},
];

export default function ThreeLooksPage() {
  const [anchors, setAnchors] = useState<Anchor[]>([]);
  const [productId, setProductId] = useState("N-P-DENIM");
  const [variantId, setVariantId] = useState("N-V-DENIM-28");
  const [budget, setBudget] = useState("250");
  const [clothingSize, setClothingSize] = useState("M");
  const [shoeSize, setShoeSize] = useState("US 8");
  const [denimSize, setDenimSize] = useState("28");
  const [alreadyOwned, setAlreadyOwned] = useState(false);
  const [result, setResult] = useState<ThreeLooksResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const [added, setAdded] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let mounted = true;
    api<Anchor[]>("/customer/style/anchors", {role:"customer-c3"})
      .then(rows => {
        if (!mounted) return;
        setAnchors(rows);
        if (!rows.some(r => r.product_id === productId)) {
          setProductId(rows[0]?.product_id || "");
          setVariantId(rows[0]?.variants[0]?.variant_id || "");
        }
      })
      .catch(e => { if (mounted) setError(e instanceof Error ? e.message : "Unable to load styling products."); });
    return () => { mounted = false; };
  }, []); // Intentional one-time loading; don't reset selection while editing.

  const selected = anchors.find(a => a.product_id === productId);
  const variant = selected?.variants.find(v => v.variant_id === variantId) || selected?.variants[0];
  const selectedVariantId = variant?.variant_id || "";
  const clear = () => { setResult(null); setError(""); setNotice(""); setAdded([]); };

  async function generate() {
    const dollars = Number(budget);
    if (!selectedVariantId || (!alreadyOwned && variant?.available_quantity === 0) || !Number.isFinite(dollars) || dollars < 10 || dollars > 10000) {
      setError("Choose an in-stock item (or mark it already owned) and a budget from $10 to $10,000."); return;
    }
    setBusy(true); clear();
    try {
      const response = await api<ThreeLooksResult>("/customer/style/three-looks", {
        method: "POST", role: "customer-c3",
        data: {anchor_variant_id: selectedVariantId, budget_cents: Math.round(dollars * 100),
          clothing_size: clothingSize, shoe_size: shoeSize, denim_size: denimSize,
          already_owned: alreadyOwned},
      });
      setResult(response);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not build your looks."); }
    finally { setBusy(false); }
  }

  async function add(item: LookItem) {
    if (item.already_owned || added.includes(item.variant_id)) return;
    setAdding(item.variant_id); setError(""); setNotice("");
    try {
      await api("/customer/cart/items", {method: "POST", role: "customer-c3",
        data: {variant_id: item.variant_id, quantity: 1,
          idempotency_key: `three-looks-${crypto.randomUUID()}`}});
      setAdded(prev => [...prev, item.variant_id]);
      setNotice(`${item.title} added to your cart. No order or payment was created.`);
      window.dispatchEvent(new Event("retailai:cart-updated"));
    } catch (e) {setError(e instanceof Error ? e.message : "Unable to add this item. Inventory may have changed.");}
    finally {setAdding(null);}
  }

  return <div className="stylelab three-looks">
    <div className="stylelab-ribbon"><ShieldCheck size={13}/> SYNTHETIC DEMO · VERIFIED VARIANTS · NO AUTOMATIC CART ACTIONS</div>
    <header className="stylelab-header">
      <Link className="stylelab-back" href="/shop/style"><ArrowLeft size={17}/> Style Studio</Link>
      <Link className="stylelab-brand" href="/shop">northstar<span>.</span><small>RETAILAI / THREE LOOKS</small></Link>
      <button type="button" className="stylelab-chat" onClick={() => window.dispatchEvent(new CustomEvent("retailai:open-assistant"))}><Sparkles size={16}/> Ask RetailAI</button>
    </header>
    <main className="stylelab-shell">
      <section className="three-looks-hero">
        <div><span className="stylelab-eyebrow"><Layers3 size={15}/> RETAILAI / STYLE STUDIO / 02</span>
          <h1>One item.<br/><em>Three different looks.</em></h1>
          <p>Pick an item you love. We'll build casual, office, and evening outfits around that exact variant with verified prices and sizes.</p>
        </div>
        <div className="three-looks-hero-art" aria-hidden="true"><span>01</span><span>02</span><span>03</span></div>
      </section>
      <section className="stylelab-workspace">
        <div className="stylelab-form">
          <div className="stylelab-sectiontop"><div className="stylelab-number">01</div><div><h2>Choose your hero piece</h2><p>The same item will appear in all three looks.</p></div></div>
          <label className="stylelab-label" htmlFor="hero-product">Selected product</label>
          <select id="hero-product" className="three-looks-select" value={selected?.product_id || ""} onChange={e => {
            const next = anchors.find(a => a.product_id === e.target.value); setProductId(e.target.value);
            setVariantId(next?.variants[0]?.variant_id || ""); clear();
          }}>{anchors.map(a => <option key={a.product_id} value={a.product_id}>{a.title}</option>)}</select>
          <label className="stylelab-label" htmlFor="hero-variant">Color / size</label>
          <select id="hero-variant" className="three-looks-select" value={selectedVariantId} onChange={e => {setVariantId(e.target.value); clear();}}>
            {selected?.variants.map(v => <option key={v.variant_id} value={v.variant_id}>{v.color} · {v.size} · {usd(v.price_cents)} · {v.available_quantity} in stock</option>)}
          </select>
          <label className="three-looks-own"><input type="checkbox" checked={alreadyOwned} onChange={e => {setAlreadyOwned(e.target.checked);clear();}}/>
            <span>I already own this piece. Only budget for the other items.</span></label>
          <label className="stylelab-label" htmlFor="three-looks-budget">Budget for each complete look / additions (USD)</label>
          <div className="stylelab-budgetfield"><span>$</span><input id="three-looks-budget" type="number" min="10" max="10000" value={budget} onChange={e => {setBudget(e.target.value);clear();}}/></div>
          <div className="stylelab-quickbudgets">{[200,250,300,400].map(b => <button type="button" key={b} onClick={() => {setBudget(String(b)); clear();}}>${b}</button>)}</div>
          <div className="stylelab-sizes">
            <label>Clothing size<select value={clothingSize} onChange={e => {setClothingSize(e.target.value);clear();}}>{["XS","S","M","L","XL"].map(s => <option key={s}>{s}</option>)}</select></label>
            <label>Shoe size<select value={shoeSize} onChange={e => {setShoeSize(e.target.value);clear();}}>{["US 7","US 8","US 9"].map(s => <option key={s}>{s}</option>)}</select></label>
            <label>Denim waist<select value={denimSize} onChange={e => {setDenimSize(e.target.value);clear();}}>{["26","28","30","32"].map(s => <option key={s}>{s}</option>)}</select></label>
          </div>
          <button type="button" className="stylelab-generate" disabled={busy || !selectedVariantId} onClick={() => void generate()}><Sparkles size={17}/>{busy ? "Building your looks…" : "Create three looks"}<ArrowRight size={16}/></button>
          <p className="stylelab-disclaimer">Curated rule-based combinations from the synthetic store. Your selection is checked against real local stock. No image generation, payment, or automatic cart changes.</p>
        </div>
        <div className="stylelab-results" aria-live="polite">
          <div className="stylelab-sectiontop"><div className="stylelab-number">02</div><div><h2>Your three looks</h2><p>Same hero item · Different occasions · Verified catalog</p></div></div>
          {!result && <div className="stylelab-empty"><div><Layers3 size={35}/></div><h3>One piece, three possibilities.</h3><p>Select a product and see how one item can work across your week.</p><span>YOUR LOOKS WILL APPEAR HERE</span></div>}
          {result && !result.looks.length && <div className="stylelab-notfit"><h3>Can't style this exact item</h3><p>{result.message}</p></div>}
          {result?.looks.map((look, index) => <article className="three-look-card" key={look.occasion}>
            <div className="three-look-card-header"><div><span>LOOK {String(index+1).padStart(2,"0")} / {look.occasion.toUpperCase()}</span><h3>{OCCASIONS[index].title.split(" / ")[1]}</h3><small>{OCCASIONS[index].label}</small></div>
              {look.to_buy_cents !== null && <div className="three-look-price"><span>TO BUY</span><strong>{usd(look.to_buy_cents)}</strong><small>{look.feasible ? `${usd(look.remaining_cents || 0)} left` : `${usd(look.shortfall_cents || 0)} over budget`}</small></div>}</div>
            {look.feasible ? <div className="three-look-products">{look.items.map(item => <div className="three-look-item" key={item.variant_id}>
              <ProductPhoto productId={item.product_id} title={item.title} className="three-look-item-photo"/>
              <div className="three-look-item-text"><strong>{item.title}</strong><span>{item.role === "hero" ? "YOUR HERO · " : ""}{item.color} · {item.size} · {item.already_owned ? "already owned" : `${item.available_quantity} in stock`}</span></div>
              <b>{usd(item.price_cents)}</b>
              {item.already_owned ? <span className="three-look-owned">Owned</span> : <button type="button" disabled={adding !== null || added.includes(item.variant_id)} onClick={() => void add(item)}>{added.includes(item.variant_id) ? "Added" : adding === item.variant_id ? "Adding" : "Add"}</button>}
            </div>)}</div> : <p className="three-look-unavailable">{look.message}{look.missing_roles.length ? ` Missing: ${look.missing_roles.join(", ")}.` : ""}</p>}
          </article>)}
          {result?.looks.length ? <p className="three-looks-summary">Budget is checked separately for each look. Shared items only need to be added once. Prices and availability are verified again by the cart service.</p> : null}
          {error && <div role="alert" className="stylelab-error">{error}</div>}
          {notice && <div role="status" className="stylelab-notice">{notice}</div>}
        </div>
      </section>
    </main>
  </div>;
}

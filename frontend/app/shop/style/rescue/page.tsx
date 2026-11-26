"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Camera, Check, ImagePlus, RefreshCw, ShieldCheck, ShoppingBag, Sparkles, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import ProductPhoto from "@/components/ProductPhoto";
import "../style.css";
import "./rescue.css";

type Garment = "jeans" | "skirt" | "dress" | "top";
type Occasion = "casual" | "office" | "evening";
type Detection = { item_type: Garment | "other"; color: string; pattern: string; description: string; confidence: "high" | "medium" | "low"; single_item_visible: boolean };
type Analysis = { detected: Detection; provider: string; model: string; image_saved: false; notice: string };
type Item = { product_id: string; variant_id: string; title: string; category: string; color: string; size: string; price_cents: number; available_quantity: number; role: string };
type Look = { feasible: boolean; occasion: Occasion; owned_item: { item_type: Garment; color: string; already_owned: true; price_cents: 0 }; budget_cents: number; subtotal_cents: number | null; remaining_cents: number | null; shortfall_cents: number | null; missing_roles: string[]; items: Item[]; message: string; cart_updated: false; image_saved: false };
const usd = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n / 100);

export default function RescuePage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [detected, setDetected] = useState<Detection | null>(null);
  const [type, setType] = useState<Garment>("jeans");
  const [color, setColor] = useState("Blue");
  const [occasion, setOccasion] = useState<Occasion>("casual");
  const [budget, setBudget] = useState("250");
  const [clothingSize, setClothingSize] = useState("M");
  const [shoeSize, setShoeSize] = useState("US 8");
  const [denimSize, setDenimSize] = useState("28");
  const [analyzing, setAnalyzing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<Look | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const [added, setAdded] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!file) { setPreview(""); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function chooseFile(next: File | null) {
    setFile(next);
    setDetected(null); setResult(null); setAdded([]); setError(""); setNotice("");
  }

  async function analyze() {
    if (!file) { setError("Choose a garment photo first."); return; }
    if (file.size > 4 * 1024 * 1024 || !["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setError("Use a JPEG, PNG or WebP image under 4 MB."); return;
    }
    setAnalyzing(true); setError(""); setDetected(null); setResult(null);
    try {
      const data = new FormData(); data.append("image", file);
      const response = await fetch("/api/demo/customer/style/rescue/analyze", {
        method: "POST", headers: { "x-demo-role": "customer-c3" }, body: data, cache: "no-store",
      });
      const payload: Analysis & { detail?: string } = await response.json();
      if (!response.ok) throw new Error(payload.detail || `Vision request failed (${response.status})`);
      setDetected(payload.detected);
      if (payload.detected.item_type !== "other") setType(payload.detected.item_type);
      setColor(payload.detected.color);
      setNotice("Vision analysis complete. Verify the item type and color below before building your look.");
    } catch (e) {
      setError(`${e instanceof Error ? e.message : "Image analysis failed."} You may select the garment type manually.`);
    } finally { setAnalyzing(false); }
  }

  async function generate() {
    const dollars = Number(budget);
    if (!file) { setError("Upload a photo of the item you own first."); return; }
    if (!Number.isFinite(dollars) || dollars < 10 || dollars > 10000) { setError("Enter a budget between $10 and $10,000."); return; }
    setGenerating(true); setError(""); setNotice(""); setResult(null); setAdded([]);
    try {
      const row = await api<Look>("/customer/style/rescue/recommend", {
        method: "POST", role: "customer-c3",
        data: { owned_type: type, owned_color: color.trim() || "Unknown", occasion,
          budget_cents: Math.round(dollars * 100), clothing_size: clothingSize,
          shoe_size: shoeSize, denim_size: denimSize },
      });
      setResult(row);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not create your outfit."); }
    finally { setGenerating(false); }
  }

  async function add(item: Item) {
    if (added.includes(item.variant_id)) return;
    setAdding(item.variant_id); setError(""); setNotice("");
    try {
      await api("/customer/cart/items", { method: "POST", role: "customer-c3",
        data: { variant_id: item.variant_id, quantity: 1,
          idempotency_key: `style-rescue-${crypto.randomUUID()}` } });
      setAdded(prev => [...prev, item.variant_id]);
      setNotice(`${item.title} added to your cart. Your uploaded clothing item was not added.`);
      window.dispatchEvent(new Event("retailai:cart-updated"));
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to add product. Stock may have changed."); }
    finally { setAdding(null); }
  }

  return <div className="stylelab rescue">
    <div className="stylelab-ribbon"><ShieldCheck size={13}/> SYNTHETIC STORE · GROQ VISION · OWNED ITEM IS NEVER CHARGED</div>
    <header className="stylelab-header">
      <Link className="stylelab-back" href="/shop/style"><ArrowLeft size={17}/> Style Studio</Link>
      <Link className="stylelab-brand" href="/shop">northstar<span>.</span><small>RETAILAI / STYLE RESCUE</small></Link>
      <button className="stylelab-chat" type="button" onClick={() => window.dispatchEvent(new CustomEvent("retailai:open-assistant"))}><Sparkles size={15}/> Ask RetailAI</button>
    </header>
    <main className="stylelab-shell">
      <div className="rescue-hero"><div><div className="stylelab-eyebrow"><Camera size={15}/> RETAILAI / STYLE STUDIO / 03</div>
        <h1>Style what<br/><em>you already own.</em></h1>
        <p>Upload a photo of one garment. Groq Vision identifies it, then we find matching pieces from our actual store inventory. Your own item is never added to your cart.</p></div>
        <div className="rescue-hero-mark"><ImagePlus size={66}/><span>YOUR WARDROBE × OUR CATALOG</span></div></div>
      <section className="stylelab-workspace">
        <div className="stylelab-form">
          <div className="stylelab-sectiontop"><div className="stylelab-number">01</div><div><h2>Upload your piece</h2><p>Flat-lay photos work best. One item per image.</p></div></div>
          <label className="rescue-upload" htmlFor="rescue-photo">
            {preview ? <img src={preview} alt="Preview of the item you selected"/> : <><ImagePlus size={40}/><strong>Choose a clothing photo</strong><span>JPEG, PNG or WebP · maximum 4 MB</span></>}
          </label>
          <input id="rescue-photo" type="file" accept="image/jpeg,image/png,image/webp" onChange={e => chooseFile(e.target.files?.[0] || null)} className="rescue-hidden-input"/>
          {file && <div className="rescue-photo-meta"><span>{file.name}</span><button type="button" onClick={() => chooseFile(null)}>Remove photo</button></div>}
          <button type="button" className="rescue-analyze" onClick={() => void analyze()} disabled={!file || analyzing || generating}><Camera size={17}/>{analyzing ? "Analyzing with Groq Vision…" : "Analyze my photo"}</button>
          <p className="stylelab-disclaimer">The photo is sent to Groq for visual analysis. RetailAI does not save it to our database. Avoid photos containing people or sensitive information.</p>
          <div className="rescue-detection">
            <h3>{detected ? "Vision result — review before styling" : "Confirm your garment details"}</h3>
            {detected && <p className="rescue-detected">{detected.description} · {detected.confidence} confidence{!detected.single_item_visible ? " · multiple or unclear items" : ""}</p>}
            <label>Item type<select value={type} onChange={e => {setType(e.target.value as Garment);setResult(null);}}>
              <option value="jeans">Jeans / denim trousers</option><option value="skirt">Skirt</option><option value="dress">Dress</option><option value="top">Shirt / blouse / top</option>
            </select></label>
            {detected?.item_type === "other" && <p className="rescue-warning"><AlertCircle size={14}/> Vision couldn't confidently identify a supported garment. Choose the correct type manually or try another photo.</p>}
            <label>Color<input maxLength={40} value={color} onChange={e => {setColor(e.target.value);setResult(null);}}/></label>
          </div>
          <label className="stylelab-label">Occasion</label>
          <div className="stylelab-occasions">{(["casual","office","evening"] as Occasion[]).map((o,i) => <button key={o} type="button" aria-pressed={occasion === o} className={occasion === o ? "stylelab-occasion selected" : "stylelab-occasion"} onClick={() => {setOccasion(o);setResult(null);}}><span>0{i+1}</span><strong>{o === "casual" ? "Everyday" : o === "office" ? "Office" : "Evening"}</strong></button>)}</div>
          <label className="stylelab-label" htmlFor="rescue-budget">Budget for NEW items (USD)</label>
          <div className="stylelab-budgetfield"><span>$</span><input id="rescue-budget" type="number" min="10" max="10000" value={budget} onChange={e => {setBudget(e.target.value);setResult(null);}}/></div>
          <div className="stylelab-quickbudgets">{[150,200,250,300].map(n => <button key={n} type="button" onClick={() => {setBudget(String(n));setResult(null);}}>${n}</button>)}</div>
          <div className="stylelab-sizes">
            <label>Clothing size<select value={clothingSize} onChange={e => setClothingSize(e.target.value)}>{["XS","S","M","L","XL"].map(s => <option key={s}>{s}</option>)}</select></label>
            <label>Shoe size<select value={shoeSize} onChange={e => setShoeSize(e.target.value)}>{["US 7","US 8","US 9"].map(s => <option key={s}>{s}</option>)}</select></label>
            <label>Denim waist<select value={denimSize} onChange={e => setDenimSize(e.target.value)}>{["26","28","30","32"].map(s => <option key={s}>{s}</option>)}</select></label>
          </div>
          <button type="button" className="stylelab-generate" disabled={!file || analyzing || generating} onClick={() => void generate()}><Sparkles size={17}/>{generating ? "Styling from the catalog…" : "Rescue my style"}<ArrowRight size={15}/></button>
        </div>
        <div className="stylelab-results" aria-live="polite">
          <div className="stylelab-sectiontop"><div className="stylelab-number">02</div><div><h2>Your shoppable look</h2><p>Your garment + verified new pieces</p></div></div>
          {!result && <div className="stylelab-empty"><div><Sparkles size={34}/></div><h3>Already yours. Newly styled.</h3><p>Upload a photo and pick your occasion. A matching look will appear here.</p><span>THE OUTFIT WILL APPEAR HERE</span></div>}
          {result && <>
            <div className="rescue-owned">{preview ? <div className="rescue-owned-photo retail-photo"><img src={preview} alt="Your uploaded item — only a local preview"/></div> : <div><Check size={18}/></div>}<section><span>ALREADY IN YOUR WARDROBE · $0 TO BUY</span><h3>{result.owned_item.color} {result.owned_item.item_type}</h3><p>Kept in your outfit · Excluded from every cart addition</p></section></div>
            {result.feasible ? <>
              <div className="stylelab-summary"><div><span>{result.occasion.toUpperCase()} · IN-STOCK ADDITIONS</span><h3>{result.items.length} pieces to complete your look</h3><p>Real synthetic catalog prices and availability</p></div><div className="stylelab-summarytotal"><span>NEW ITEMS TOTAL</span><strong>{usd(result.subtotal_cents || 0)}</strong><small>{usd(result.remaining_cents || 0)} left</small></div></div>
              <div className="stylelab-items">{result.items.map((item,i) => <div className="stylelab-item" key={item.variant_id}>
                <div className={`stylelab-item-art tone-${i%4}`}><ProductPhoto productId={item.product_id} title={item.title}/><span className="stylelab-art-label">{item.role.toUpperCase()}</span></div>
                <div className="stylelab-item-details"><span>{item.category.toUpperCase()} / {item.color.toUpperCase()}</span><h4>{item.title}</h4><p>{item.size} · {item.available_quantity} in stock</p><button type="button" onClick={() => void add(item)} disabled={adding !== null || added.includes(item.variant_id)}><ShoppingBag size={14}/>{added.includes(item.variant_id) ? "Added to cart" : adding === item.variant_id ? "Adding…" : "Add to cart"}</button></div>
                <strong className="stylelab-item-price">{usd(item.price_cents)}</strong></div>)}</div>
            </> : <div className="stylelab-notfit"><AlertCircle size={26}/><h3>Not a complete outfit yet</h3><p>{result.message}</p>{result.shortfall_cents !== null && result.shortfall_cents > 0 && <p>Increase your budget by at least <strong>{usd(result.shortfall_cents)}</strong> or try another occasion.</p>}{result.missing_roles.length > 0 && <p>Unavailable sizes for: {result.missing_roles.join(", ")}.</p>}</div>}
            <p className="stylelab-bottomnote"><ShieldCheck size={15}/> Curated templates, not image similarity ranking. Prices and stock are verified against the cart service when you add an item.</p>
          </>}
          {error && <div role="alert" className="stylelab-error">{error}</div>}
          {notice && <div role="status" className="stylelab-notice">{notice}</div>}
        </div>
      </section>
    </main>
  </div>;
}

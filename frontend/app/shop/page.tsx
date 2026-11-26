"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { ArrowRight, CheckCircle2, LockKeyhole, Package, ShieldCheck, Truck, UserRound, MessageCircle, Sparkles, ShoppingBag, Heart, Search, Star, Menu } from "lucide-react";
import { api, type Product } from "@/lib/api";
import RetailCatalog from "./retail-catalog";
import "./store.css";

type Profile = { id: string; display_name: string; environment: string };
type Order = {
  id: string; status: string; tracking_number: string | null; total_cents: number;
  currency: string; delivered_at: string | null;
  items: { id: string; product_title: string; size: string; color: string; quantity: number }[];
};
const money = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n / 100);
const label = (s: string) => s.replaceAll("_", " ").replace(/\b\w/g, m => m.toUpperCase());
const customerGet = <T,>(path: string) => api<T>(path, { role: "customer-c3" });

function openAssistant(orderId?: string) {
  window.dispatchEvent(new CustomEvent("retailai:open-assistant", { detail: { orderId } }));
}

const collections = [
  { name: "DRESSES", category: "dresses", src: "/images/products/wrap-dress.webp" },
  { name: "DENIM", category: "bottoms", src: "/images/products/straight-leg-jeans.webp" },
  { name: "SHOES", category: "footwear", src: "/images/products/court-sneakers.webp" },
  { name: "BAGS", category: "bags", src: "/images/products/crossbody-bag.webp" },
  { name: "ACCESSORIES", category: "accessories", src: "/images/products/hoop-earrings.webp" },
  { name: "ACTIVEWEAR", category: "leggings", src: "/images/products/sports-bra.webp" },
];

export default function ShopPage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [catalog, setCatalog] = useState<Product[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [customer, products, customerOrders] = await Promise.all([
        customerGet<Profile>("/customer/profile"),
        customerGet<Product[]>("/customer/catalog"),
        customerGet<Order[]>("/customer/orders"),
      ]);
      setProfile(customer); setCatalog(products); setOrders(customerOrders); setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Store data unavailable");
    }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const handler = () => void refresh();
    window.addEventListener("retailai:order-created", handler);
    return () => window.removeEventListener("retailai:order-created", handler);
  }, [refresh]);
  const browseCategory = (category: string) => {
    window.dispatchEvent(new CustomEvent("retailai:catalog-category", {detail:{category}}));
    document.getElementById("collection")?.scrollIntoView({behavior:"smooth"});
    setMenuOpen(false);
  };

  return <div className="store edit-store">
    <div className="edit-promo"><Star size={12} fill="currentColor"/> THE NORTHSTAR EDIT <span>•</span> NEW ARRIVALS & EVERYDAY FAVORITES <span>•</span> YOUR STYLE, YOUR RULES <a href="#collection">SHOP THE EDIT <ArrowRight size={13}/></a></div>
    <header className="store-header edit-header">
      <a href="/shop" className="edit-brand" aria-label="Northstar Edit home"><span className="edit-brand-star">✦</span><span>NORTHSTAR <em>EDIT</em><small>FASHION · LIFESTYLE · ACTIVE</small></span></a>
      <button type="button" className="edit-menu-toggle" onClick={() => setMenuOpen(s => !s)} aria-expanded={menuOpen} aria-label="Toggle categories"><Menu size={22}/></button>
      <nav className={menuOpen ? "edit-nav open" : "edit-nav"} aria-label="Main store navigation">
        <a href="#collection" onClick={() => setMenuOpen(false)}>SHOP ALL</a><button type="button" onClick={() => browseCategory("dresses")}>FASHION</button><button type="button" onClick={() => browseCategory("footwear")}>SHOES</button><button type="button" onClick={() => browseCategory("bags")}>BAGS</button><button type="button" onClick={() => browseCategory("accessories")}>ACCESSORIES</button><Link href="/shop/style">STYLE STUDIO</Link>
      </nav>
      <div className="edit-header-actions">
        <button type="button" title="Ask NOVA to find an item" aria-label="Ask NOVA to find an item" onClick={() => openAssistant()}><Search size={18}/></button>
        <a href="#collection" title="Browse styles" aria-label="Browse styles"><Heart size={18}/></a>
        <button type="button" title="View your cart" aria-label="View your cart" onClick={() => window.dispatchEvent(new Event("retailai:open-cart"))}><ShoppingBag size={18}/></button>
        <span className="edit-customer-name"><UserRound size={15}/>{profile?.display_name || "Demo customer"}</span>
      </div>
    </header>

    <main className="store-main edit-main">
      <section className="store-hero edit-hero" aria-label="Explore Northstar Edit fashion and lifestyle">
        <div className="edit-hero-words">
          <div className="edit-hero-kicker">THE NORTHSTAR EDIT / 2026 COLLECTION</div>
          <h1>FASHION &<br/>LIFESTYLE<br/><em>FOR EVERY DAY.</em></h1>
          <p>A curated edit of modern fashion, effortless essentials and a little activewear. Discover your next favorite look with NOVA.</p>
          <div className="edit-hero-buttons"><a href="#collection" className="edit-hero-primary">SHOP THE EDIT <ArrowRight size={16}/></a><button type="button" className="edit-hero-outline" onClick={() => openAssistant()}><Sparkles size={16}/> GET A STYLE RECOMMENDATION</button></div>
          <div className="edit-hero-signals"><span>✧ &nbsp; FASHION FOR ALL</span><span>✳ &nbsp; EVERYDAY ESSENTIALS</span><span>◇ &nbsp; CURATED COLLECTIONS</span></div>
        </div>
        <div className="edit-hero-photo"><Image src="/images/brand/northstar-editorial-hero.webp" alt="Editorial portrait showcasing a chic blazer and burgundy fashion styling" fill priority sizes="(max-width: 700px) 100vw, 52vw"/><span className="edit-hero-star" aria-hidden="true">✦</span><span className="edit-hero-photo-caption">THE EDIT / MODERN EVERYDAY STYLE</span></div>
      </section>

      <section id="categories" className="edit-category-strip" aria-label="Shop by category">
        <div className="edit-category-heading"><span>FIND YOUR FAVORITES</span><h2>SHOP<br/>BY CATEGORY</h2></div>
        {collections.map(item => <button key={item.name} className="edit-category" type="button" onClick={() => browseCategory(item.category)}><span className="edit-category-photo"><Image src={item.src} alt={item.name.toLowerCase()} width={205} height={146}/></span><strong>{item.name}<ArrowRight size={14}/></strong></button>)}
      </section>
      {error && <div className="store-notice store-error" role="alert">{error}. Start FastAPI on port 8000 to load your catalog and orders.</div>}
      <section className="edit-intro-row"><div><span className="edit-eyebrow">NORTHSTAR PICKS / SELECTED FOR YOU</span><h2>CURATED<br/>FOR YOU.</h2><p>Pieces for wherever life takes you — from evening dresses to everyday denim and easygoing essentials.</p></div><div className="edit-intro-photos">{[
        {src:"/images/products/wrap-dress.webp",alt:"Wrap dress"},
        {src:"/images/products/straight-leg-jeans.webp",alt:"Straight-leg jeans"},
        {src:"/images/products/crossbody-bag.webp",alt:"Crossbody bag"},
        {src:"/images/products/court-sneakers.webp",alt:"Court sneakers"}
      ].map(item=><Image key={item.src} src={item.src} alt={item.alt} width={340} height={320}/>)}</div></section>
      <section className="retail-style-promo edit-style-promo"><div><span>✦ &nbsp; YOUR PERSONAL STYLIST, ON DEMAND</span><h2>Good style is personal.</h2><p>Explore budget-friendly outfits, three-look styling and image-assisted wardrobe ideas with NOVA.</p></div><Link href="/shop/style">EXPLORE STYLE STUDIO <ArrowRight size={15}/></Link></section>
      <RetailCatalog products={catalog}/>
      <section id="orders" className="store-section store-orders-section">
        <div className="store-section-heading"><div><span className="store-eyebrow dark">YOUR NORTHSTAR EDIT ACCOUNT</span><h2>Your orders, in one place.</h2></div><span className="store-muted"><LockKeyhole size={14}/> Private demo order history</span></div>
        <div className="store-order-cards">{orders.map(o=><article key={o.id} className="store-order-card">
          <div className="store-order-top"><div><span>ORDER REFERENCE</span><h3>{o.id}</h3></div><span className="store-order-status"><CheckCircle2 size={13}/>{label(o.status)}</span></div>
          <div className="store-order-items"><Package size={18}/><span>{o.items.map(i=>`${i.product_title} · ${i.size}`).join(", ")}</span></div>
          <div className="store-order-footer"><span><Truck size={14}/>{o.tracking_number || "Tracking pending"}</span><strong>{money(o.total_cents)}</strong></div>
          <button type="button" className="retail-order-help" onClick={() => openAssistant(o.id)}><MessageCircle size={14}/> Need help with this order? <ArrowRight size={13}/></button>
        </article>)}</div>
        {!orders.length && !error && <p className="edit-empty-orders">Your demo orders will appear here after you complete a confirmed sandbox checkout.</p>}
      </section>
    </main>
    <footer className="store-footer edit-footer"><strong><span>✦</span> NORTHSTAR EDIT</strong><span>PERSONAL STYLE. SMARTER SHOPPING.</span><button type="button" onClick={() => openAssistant()}>CHAT WITH NOVA <ArrowRight size={14}/></button><a href="/operations">STAFF WORKSPACE <ArrowRight size={14}/></a></footer>
  </div>;
}

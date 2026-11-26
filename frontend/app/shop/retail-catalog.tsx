"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, ChevronDown, CircleAlert, FilterX, PackageSearch, Search, ShoppingBag, SlidersHorizontal, X } from "lucide-react";
import ProductPhoto from "@/components/ProductPhoto";
import { api, type Product, type Variant } from "@/lib/api";
import "./retail-catalog.css";

const usd = (cents: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
const titleCase = (text: string) => text.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
const stock = (product: Product) => product.variants.reduce((total, variant) => total + variant.available_quantity, 0);
const displaySize = (size: string) => size === "ONE" ? "One size" : size;

function Visual({ product, detailed = false }: { product: Product; detailed?: boolean }) {
  return <div className={`retail-product-visual retail-product-image ${detailed ? "detailed" : ""}`}>
    <ProductPhoto productId={product.id} title={product.title} eager={detailed} />
    <span className="retail-visual-caption">N / RETAILAI · {titleCase(product.category)}</span>
  </div>;
}

type SortBy = "recommended" | "price_asc" | "price_desc" | "name";

export default function RetailCatalog({ products }: { products: Product[] }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [size, setSize] = useState("");
  const [color, setColor] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [inStock, setInStock] = useState(false);
  const [sort, setSort] = useState<SortBy>("recommended");
  const [results, setResults] = useState<Product[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Product | null>(null);
  const [selectedVariantId, setSelectedVariantId] = useState("");
  const [cartBusy, setCartBusy] = useState(false);
  const [cartError, setCartError] = useState("");

  const categories = useMemo(() => [...new Set(products.map(p => p.category))].sort(), [products]);
  useEffect(() => {
    const onCategory = (event: Event) => {
      const requested = (event as CustomEvent<{ category?: string }>).detail?.category;
      if (typeof requested === "string" && products.some(p => p.category === requested)) {
        setCategory(requested);
      }
    };
    window.addEventListener("retailai:catalog-category", onCategory);
    return () => window.removeEventListener("retailai:catalog-category", onCategory);
  }, [products]);
  const sizes = useMemo(() => [...new Set(products.flatMap(p => p.variants.map(v => v.size)))].sort(), [products]);
  const colors = useMemo(() => [...new Set(products.flatMap(p => p.variants.map(v => v.color)))].sort(), [products]);
  const invalidPrices = Boolean(minPrice && maxPrice && Number(minPrice) > Number(maxPrice));
  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (category) params.set("category", category);
    if (size) params.set("size", size);
    if (color) params.set("color", color);
    if (minPrice) params.set("min_price_cents", String(Math.round(Number(minPrice) * 100)));
    if (maxPrice) params.set("max_price_cents", String(Math.round(Number(maxPrice) * 100)));
    if (inStock) params.set("in_stock", "true");
    return params.toString();
  }, [query, category, size, color, minPrice, maxPrice, inStock]);

  useEffect(() => {
    if (!queryString) { setResults(null); setError(""); setLoading(false); return; }
    if (invalidPrices) { setResults([]); setError("Minimum price must not exceed maximum price."); setLoading(false); return; }
    let active = true;
    const task = setTimeout(async () => {
      setLoading(true); setError("");
      try {
        const data = await api<Product[]>(`/customer/catalog?${queryString}`, { role: "customer-c3" });
        if (active) setResults(data);
      } catch (e) {
        if (active) { setResults([]); setError(e instanceof Error ? e.message : "Catalog lookup failed."); }
      } finally { if (active) setLoading(false); }
    }, 250);
    return () => { active = false; clearTimeout(task); };
  }, [queryString, invalidPrices]);

  const items = useMemo(() => {
    const list = [...(results ?? products)];
    if (sort === "price_asc") list.sort((a, b) => Math.min(...a.variants.map(v => v.price_cents)) - Math.min(...b.variants.map(v => v.price_cents)));
    if (sort === "price_desc") list.sort((a, b) => Math.min(...b.variants.map(v => v.price_cents)) - Math.min(...a.variants.map(v => v.price_cents)));
    if (sort === "name") list.sort((a, b) => a.title.localeCompare(b.title));
    return list;
  }, [results, products, sort]);

  function clear() {
    setQuery(""); setCategory(""); setSize(""); setColor("");
    setMinPrice(""); setMaxPrice(""); setInStock(false); setSort("recommended");
    setResults(null); setError("");
  }
  function openProduct(item: Product) { setCartError(""); setSelected(item); setSelectedVariantId(item.variants.find(v => v.available_quantity > 0)?.id || item.variants[0]?.id || ""); }
  const activeVariant: Variant | undefined = selected?.variants.find(v => v.id === selectedVariantId);
  async function addToCart() {
    if (!activeVariant || cartBusy || activeVariant.available_quantity < 1) return;
    setCartError(""); setCartBusy(true);
    try {
      await api("/customer/cart/items", { role: "customer-c3", method: "POST", data: {
        variant_id: activeVariant.id, quantity: 1, idempotency_key: crypto.randomUUID(),
      }});
      setSelected(null);
      window.dispatchEvent(new Event("retailai:cart-updated"));
      window.dispatchEvent(new Event("retailai:open-cart"));
    } catch (e) {
      setCartError(e instanceof Error ? e.message : "Unable to add to cart");
    } finally { setCartBusy(false); }
  }
  useEffect(() => {
    if (!selected) return;
    const handleEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setSelected(null); };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [selected]);

  return <section id="collection" className="store-section retail-catalog-section">
    <div className="store-section-heading">
      <div><span className="store-eyebrow dark">NORTHSTAR / RETAILAI CATALOG</span><h2>Find your next favorite.</h2></div>
      <span className="store-muted">Live local catalog · {products.length} styles</span>
    </div>
    <div className="retail-browse-banner">
      <div><strong>Thoughtfully selected. Effortlessly discovered.</strong><span>Explore apparel, footwear, bags and more. Every price and stock level comes from our demo database.</span></div>
      <span className="retail-browse-counter">{products.length.toString().padStart(2,"0")}<small>STYLES</small></span>
    </div>
    <div className="retail-category-tabs" aria-label="Shop by category">
      <button className={!category ? "active" : ""} onClick={() => setCategory("")} aria-pressed={!category}>All styles</button>
      {categories.map(item => <button key={item} className={category === item ? "active" : ""} aria-pressed={category === item} onClick={() => setCategory(category === item ? "" : item)}>{titleCase(item)}</button>)}
    </div>
    <div className="retail-filters">
      <label className="retail-search"><Search size={18} /><input aria-label="Search products" placeholder="Search styles or occasion…" value={query} onChange={e => setQuery(e.target.value.slice(0,80))} /></label>
      <label>Size <span className="retail-select"><select aria-label="Filter size" value={size} onChange={e => setSize(e.target.value)}><option value="">All sizes</option>{sizes.map(s => <option key={s} value={s}>{displaySize(s)}</option>)}</select><ChevronDown size={14}/></span></label>
      <label>Color <span className="retail-select"><select aria-label="Filter color" value={color} onChange={e => setColor(e.target.value)}><option value="">All colors</option>{colors.map(c => <option key={c} value={c}>{c}</option>)}</select><ChevronDown size={14}/></span></label>
      <label>Min $ <input className="retail-price" aria-label="Minimum price in US dollars" type="number" min="0" max="10000" step="1" placeholder="0" value={minPrice} onChange={e => setMinPrice(e.target.value)} /></label>
      <label>Max $ <input className="retail-price" aria-label="Maximum price in US dollars" type="number" min="0" max="10000" step="1" placeholder="Any" value={maxPrice} onChange={e => setMaxPrice(e.target.value)} /></label>
      <label className="retail-stock-filter"><input type="checkbox" checked={inStock} onChange={e => setInStock(e.target.checked)} /> In stock</label>
    </div>
    <div className="retail-results-row">
      <div><SlidersHorizontal size={16} /><strong>{items.length} matching styles</strong><span>{loading ? "Updating from database…" : "Prices and stock reflect current synthetic records"}</span></div>
      <div className="retail-sort"><label htmlFor="retail-sort-by">Sort</label><select id="retail-sort-by" value={sort} onChange={e => setSort(e.target.value as SortBy)}><option value="recommended">Catalog order</option><option value="price_asc">Price: low to high</option><option value="price_desc">Price: high to low</option><option value="name">Name: A to Z</option></select><button type="button" onClick={clear}><FilterX size={14}/> Reset</button></div>
    </div>
    {error && <div role="alert" className="retail-catalog-error"><CircleAlert size={16}/>{error}</div>}
    <div className="retail-product-grid" aria-busy={loading}>
      {items.map(item => <article className="retail-card" key={item.id}>
        <button className="retail-visual-button" onClick={() => openProduct(item)} aria-label={`View ${item.title} details`}><Visual product={item} /></button>
        <div className="retail-card-body"><div className="retail-card-overline">{titleCase(item.category)} <span>{stock(item) > 0 ? `${stock(item)} units available` : "Out of stock"}</span></div>
          <h3>{item.title}</h3><p>{item.description}</p>
          <div className="retail-card-bottom"><strong>{usd(Math.min(...item.variants.map(v => v.price_cents)))}</strong><button type="button" onClick={() => openProduct(item)}>Sizes & details <ArrowRight size={15}/></button></div>
        </div>
      </article>)}
    </div>
    {!loading && !error && items.length === 0 && <div className="retail-no-results"><PackageSearch size={32}/><h3>No products match these filters.</h3><p>Try a different size, color, or price range.</p><button onClick={clear}>Clear filters</button></div>}
    <p className="retail-disclaimer">Product photos are AI-generated illustrations of our fictional demo catalog. Prices, cart actions, and sandbox checkout use verified local business data; no live payment occurs.</p>

    {selected && <div className="retail-dialog-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setSelected(null); }}>
      <div className="retail-product-dialog" role="dialog" aria-modal="true" aria-label={`${selected.title} product details`}>
        <button className="retail-close" autoFocus onClick={() => setSelected(null)} aria-label="Close product details"><X size={20}/></button>
        <Visual product={selected} detailed />
        <div className="retail-dialog-info"><span className="store-eyebrow dark">{titleCase(selected.category)} / PRODUCT DETAILS</span>
          <h2>{selected.title}</h2><p>{selected.description}</p><div className="retail-dialog-price">{activeVariant ? usd(activeVariant.price_cents) : "—"}</div>
          <strong className="retail-variant-title">CHOOSE A SIZE / VARIANT</strong>
          <div className="retail-variant-buttons">{selected.variants.map(v => <button key={v.id} type="button" className={v.id === selectedVariantId ? "active" : ""} onClick={() => setSelectedVariantId(v.id)} aria-pressed={v.id === selectedVariantId} title={`${v.color}: ${v.available_quantity} available`}>{displaySize(v.size)}<small>{v.color}</small></button>)}</div>
          <div className={`retail-variant-status ${activeVariant && activeVariant.available_quantity === 0 ? "unavailable" : ""}`}>{activeVariant && activeVariant.available_quantity > 0 ? <Check size={17}/> : <CircleAlert size={17}/>}<span>{activeVariant ? activeVariant.available_quantity > 0 ? `${activeVariant.available_quantity} units available · ${activeVariant.color}` : "Out of stock for this variant" : "Choose a variant"}</span></div>
          <div className="retail-dialog-fineprint"><strong>Database-backed availability</strong><span>Stock is checked from synthetic business records. This view does not place a hold or submit an order.</span></div>
          {cartError && <div className="retail-catalog-error" role="alert"><CircleAlert size={15}/>{cartError}</div>}
          <button type="button" className="retail-dialog-done" disabled={cartBusy || !activeVariant || activeVariant.available_quantity < 1} onClick={() => void addToCart()}><ShoppingBag size={16}/>{cartBusy ? "Adding…" : "Add to cart"} <ArrowRight size={15}/></button>
          <button type="button" className="retail-dialog-secondary" onClick={() => setSelected(null)}>Continue browsing</button>
        </div>
      </div>
    </div>}
  </section>;
}

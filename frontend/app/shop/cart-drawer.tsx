"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Minus, Plus, RefreshCcw, ShieldCheck, ShoppingCart, Trash2, X, CheckCircle2, ClipboardCheck } from "lucide-react";
import { api, type CustomerCart, type CheckoutPreview, type CheckoutReceipt } from "@/lib/api";
import ProductPhoto from "@/components/ProductPhoto";
import "./cart-drawer.css";

const money = (cents: number) => new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD",
}).format(cents / 100);
const customerCart = <T,>(path: string, init?: { method?: "GET" | "POST" | "PATCH" | "DELETE"; data?: unknown }) =>
  api<T>(path, { ...init, role: "customer-c3" });

export default function CartDrawer() {
  const [open, setOpen] = useState(false);
  const [cart, setCart] = useState<CustomerCart | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [checkout, setCheckout] = useState<CheckoutPreview | null>(null);
  const [checkoutConfirmed, setCheckoutConfirmed] = useState(false);
  const [receipt, setReceipt] = useState<CheckoutReceipt | null>(null);
  // Persist this key across retries of the same confirmed checkout request.
  const checkoutKey = useRef<string | null>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const refresh = useCallback(async () => {
    try {
      const latest = await customerCart<CustomerCart>("/customer/cart");
      setCart(latest); setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cart is unavailable");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const show = () => { setOpen(true); void refresh(); };
    const updated = () => { setCheckout(null); setCheckoutConfirmed(false); void refresh(); };
    window.addEventListener("retailai:open-cart", show);
    window.addEventListener("retailai:cart-updated", updated);
    return () => {
      window.removeEventListener("retailai:open-cart", show);
      window.removeEventListener("retailai:cart-updated", updated);
    };
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
      if (event.key === "Tab" && dialog.current) {
        const targets = Array.from(dialog.current.querySelectorAll<HTMLElement>('button:not([disabled])'));
        if (!targets.length) return;
        const first = targets[0], last = targets[targets.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    closeRef.current?.focus();
    window.addEventListener("keydown", handleKey);
    return () => { window.removeEventListener("keydown", handleKey); previous?.focus?.(); };
  }, [open]);

  async function setQuantity(variantId: string, quantity: number) {
    if (quantity < 1) return;
    setBusy(variantId); setError("");
    try {
      const next = await customerCart<CustomerCart>(`/customer/cart/items/${encodeURIComponent(variantId)}`,
        { method: "PATCH", data: { quantity } });
      setCart(next); setCheckout(null); setCheckoutConfirmed(false);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to update the quantity"); }
    finally { setBusy(""); }
  }

  async function remove(variantId: string) {
    setBusy(variantId); setError("");
    try {
      const next = await customerCart<CustomerCart>(`/customer/cart/items/${encodeURIComponent(variantId)}`,
        { method: "DELETE" });
      setCart(next); setCheckout(null); setCheckoutConfirmed(false);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to remove the item"); }
    finally { setBusy(""); }
  }

  async function reviewCheckout() {
    setBusy("checkout-preview"); setError(""); setReceipt(null);
    try {
      const latest = await customerCart<CheckoutPreview>("/customer/checkout/preview");
      setCheckout(latest); setCheckoutConfirmed(false); checkoutKey.current = null;
    } catch (e) { setError(e instanceof Error ? e.message : "Checkout preview unavailable"); }
    finally { setBusy(""); }
  }

  async function placeOrder() {
    if (!checkout || !checkoutConfirmed || busy) return;
    setBusy("checkout-confirm"); setError("");
    try {
      if (!checkoutKey.current) checkoutKey.current = `retail-checkout-${crypto.randomUUID()}`;
      const placed = await customerCart<CheckoutReceipt>("/customer/checkout/confirm", {
        method: "POST", data: { quote_token: checkout.quote_token,
        idempotency_key: checkoutKey.current, confirmed: true },
      });
      setReceipt(placed); setCheckout(null); setCheckoutConfirmed(false);
      checkoutKey.current = null;
      await refresh();
      window.dispatchEvent(new Event("retailai:cart-updated"));
      window.dispatchEvent(new Event("retailai:order-created"));
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unable to create a sandbox order";
      setError(message);
      if (message.toLowerCase().includes("changed") || message.toLowerCase().includes("empty")) {
        setCheckout(null); setCheckoutConfirmed(false); checkoutKey.current = null;
        await refresh();
      }
    } finally { setBusy(""); }
  }

  return <div className="retail-cart-root">
    <button type="button" className="retail-cart-fab" aria-label={`Open shopping cart, ${cart?.item_count ?? 0} items`} onClick={() => window.dispatchEvent(new Event("retailai:open-cart"))}>
      <ShoppingCart size={23}/><span>My cart</span><strong>{cart?.item_count ?? 0}</strong>
    </button>
    {open && <>
      <button type="button" className="retail-cart-backdrop" aria-label="Close shopping cart" onClick={() => setOpen(false)}/>
      <div className="retail-cart-drawer" role="dialog" aria-modal="true" aria-label="Your shopping cart" ref={dialog}>
        <div className="retail-cart-header"><div><small>RETAILAI / YOUR BAG</small><h2>Shopping cart <span>({cart?.item_count ?? 0})</span></h2></div><button ref={closeRef} type="button" onClick={() => setOpen(false)} aria-label="Close shopping cart"><X size={20}/></button></div>
        <div className="retail-cart-demo"><ShieldCheck size={15}/> Synthetic customer N-C3 · Local demo</div>
        <div className="retail-cart-body">
          {error && <p className="retail-cart-error" role="alert">{error}</p>}
          {!cart && !error && <p className="retail-cart-empty">Loading your cart…</p>}
          {cart && cart.items.length === 0 && <div className="retail-cart-empty"><ShoppingCart size={38}/><strong>Your bag is ready.</strong><p>Browse the collection and add styles you like.</p><button type="button" onClick={() => setOpen(false)}>Continue shopping</button></div>}
          {cart?.items.map(item => <article key={item.variant_id} className="retail-cart-item">
            <ProductPhoto productId={item.product_id} title={item.product_title} className="retail-cart-product-mark"/>
            <div className="retail-cart-item-content">
              <small>{item.category.replaceAll("_", " ").toUpperCase()}</small><h3>{item.product_title}</h3>
              <p>{item.size === "ONE" ? "One size" : item.size} · {item.color}</p>
              <div className="retail-cart-item-bottom">
                <div className="retail-cart-quantity">
                  <button type="button" aria-label={`Decrease quantity of ${item.product_title}`} disabled={!!busy || item.quantity <= 1} onClick={() => void setQuantity(item.variant_id, item.quantity - 1)}><Minus size={14}/></button>
                  <span>{item.quantity}</span>
                  <button type="button" aria-label={`Increase quantity of ${item.product_title}`} disabled={!!busy || item.quantity >= Math.min(20, item.available_quantity)} onClick={() => void setQuantity(item.variant_id, item.quantity + 1)}><Plus size={14}/></button>
                </div>
                <strong>{money(item.line_total_cents)}</strong>
                <button type="button" className="retail-cart-remove" disabled={!!busy} aria-label={`Remove ${item.product_title}`} onClick={() => void remove(item.variant_id)}><Trash2 size={16}/></button>
              </div>
              {!item.stock_ok && <p className="retail-cart-stock-warning">Stock changed: only {item.available_quantity} available. Reduce or remove this item.</p>}
            </div>
          </article>)}
        </div>
        <footer className="retail-cart-footer">
          <button type="button" className="retail-cart-refresh" onClick={() => void refresh()} disabled={!!busy}><RefreshCcw size={14}/> Refresh live stock and pricing</button>
          <div className="retail-cart-total"><span>Subtotal</span><strong>{money(cart?.subtotal_cents ?? 0)}</strong></div>
          {!receipt && !checkout && <>
            <p>Prices are refreshed from the catalog. Taxes and shipping are excluded in this demo.</p>
            <button type="button" className="retail-cart-checkout"
              disabled={!!busy || !cart?.checkout_enabled}
              onClick={() => void reviewCheckout()}>
              <ClipboardCheck size={16}/> Review sandbox checkout
            </button>
            <small>No payment is collected. Confirming creates a local, unpaid demo order.</small>
          </>}
          {checkout && !receipt && <div className="retail-cart-checkout-review" role="group" aria-label="Confirm local sandbox checkout">
            <strong>Review your demo order</strong>
            <p>{checkout.item_count} item(s) · Subtotal {money(checkout.subtotal_cents)}</p>
            <div className="retail-cart-total"><span>Total (tax/shipping not modeled)</span><strong>{money(checkout.total_cents)}</strong></div>
            <p>No real payment, shipping request or Shopify transaction. Stock will be decremented when this local order is created.</p>
            <label><input type="checkbox" checked={checkoutConfirmed}
              onChange={e => setCheckoutConfirmed(e.target.checked)}/>
              I explicitly confirm this synthetic order and understand no payment is processed.</label>
            <button type="button" className="retail-cart-checkout" disabled={!checkoutConfirmed || !!busy}
              onClick={() => void placeOrder()}>{busy === "checkout-confirm" ? "Creating order…" : "Confirm & create demo order"}</button>
            <button type="button" className="retail-cart-cancel" disabled={!!busy} onClick={() => {
              setCheckout(null); setCheckoutConfirmed(false); checkoutKey.current = null;
            }}>Cancel</button>
          </div>}
          {receipt && <div className="retail-cart-checkout-success" role="status">
            <CheckCircle2 size={25}/><strong>Demo order created</strong>
            <p>Order: <b>{receipt.order_id}</b></p>
            <p>Reference: {receipt.reference}</p>
            <p>Total: {money(receipt.total_cents)} · Payment: Not charged</p>
            <small>Stock updated in the local database. No live Shopify order or shipment.</small>
            <button type="button" className="retail-cart-cancel" onClick={() => {
              setOpen(false); window.dispatchEvent(new Event("retailai:open-orders"));
            }}>View orders in assistant</button>
          </div>}
        </footer>
      </div>
    </>}
  </div>;
}

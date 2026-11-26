import type { ReactNode } from "react";
import CustomerAssistant from "./customer-assistant";
import CartDrawer from "./cart-drawer";
import "./product-images.css";
import "./NOVA_EDIT_UI.css";
import "./premium-fashion.css";

// The widget is mounted at the /shop layout level: it is available on /shop
// and future customer routes (e.g. /shop/products/[id] or /shop/cart).
// It is intentionally NOT mounted in the internal staff dashboard.
export default function ShopLayout({ children }: { children: ReactNode }) {
  return <>{children}<CustomerAssistant/><CartDrawer/></>;
}

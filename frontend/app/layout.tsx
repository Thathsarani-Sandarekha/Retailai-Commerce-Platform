import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Northstar Edit | AI Styling & Retail Operations",
  description: "Synthetic multi-category retail storefront with customer support and a shared single-agent operations platform.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

"use client";

import { Package } from "lucide-react";
import { productImageSrc } from "@/lib/product-images";

interface Props {
  productId: string;
  title: string;
  className?: string;
  eager?: boolean;
}

/** Single image presentation shared by every customer-facing commerce view. */
export default function ProductPhoto({ productId, title, className = "", eager = false }: Props) {
  const src = productImageSrc(productId);
  return <div className={`retail-photo ${className}`.trim()}>
    {src ? <img src={src} alt={`${title} — illustrative product photograph`} loading={eager ? "eager" : "lazy"} decoding="async" />
         : <div className="retail-photo-fallback" role="img" aria-label={`No demo photograph for ${title}`}><Package size={25}/></div>}
  </div>;
}

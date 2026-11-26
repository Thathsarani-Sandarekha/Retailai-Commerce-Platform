/** Generated demo photographs. Never interpret these paths as live Shopify imagery. */
export const PRODUCT_IMAGES: Readonly<Record<string, string>> = Object.freeze({
  "N-P-LEG": "/images/products/leggings.webp",
  "N-P-TEE": "/images/products/training-tee.webp",
  "N-P-BRA": "/images/products/sports-bra.webp",
  "N-P-SHORT": "/images/products/running-shorts.webp",
  "N-P-SOCK": "/images/products/crew-socks.webp",
  "N-P-MAT": "/images/products/training-mat.webp",
  "N-P-DENIM": "/images/products/straight-leg-jeans.webp",
  "N-P-BLOUSE": "/images/products/poplin-shirt.webp",
  "N-P-SKIRT": "/images/products/midi-skirt.webp",
  "N-P-DRESS": "/images/products/wrap-dress.webp",
  "N-P-HEELS": "/images/products/block-heels.webp",
  "N-P-SNEAKERS": "/images/products/court-sneakers.webp",
  "N-P-TOTE": "/images/products/tote-bag.webp",
  "N-P-CROSSBODY": "/images/products/crossbody-bag.webp",
  "N-P-HOOPS": "/images/products/hoop-earrings.webp",
  "N-P-SUNGLASSES": "/images/products/sunglasses.webp",
});

/** Returns a trusted, bundled local asset only; never builds a URL from user input. */
export function productImageSrc(productId: string): string | null {
  return PRODUCT_IMAGES[productId] ?? null;
}

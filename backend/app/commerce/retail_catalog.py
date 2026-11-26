"""Additive synthetic multi-category catalog for the RetailAI migration.

Existing Northstar order/stock fixtures and historical records remain untouched.
This module intentionally uses the existing Product / ProductVariant schema.
All amounts are USD cents in the existing US-store sandbox.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product, ProductVariant, Tenant

# id, title, category, description, exchangeable, variants
# Variant: suffix, size, color, price_cents, available_quantity.
RETAIL_PRODUCTS = (
    ("N-P-DENIM", "Everyday Straight-Leg Jeans", "bottoms",
     "Classic blue denim jeans for casual outfits and weekend looks.", True, (
         ("26", "26", "Indigo", 6499, 7),
         ("28", "28", "Indigo", 6499, 9),
         ("30", "30", "Indigo", 6499, 6),
         ("32", "32", "Indigo", 6499, 3),
     )),
    ("N-P-BLOUSE", "Luna Poplin Shirt", "tops",
     "Relaxed ivory button-front blouse, ideal for workwear or everyday styling.", True, (
         ("S", "S", "Ivory", 4299, 8),
         ("M", "M", "Ivory", 4299, 12),
         ("L", "L", "Ivory", 4299, 5),
     )),
    ("N-P-SKIRT", "City Pleated Midi Skirt", "skirts",
     "Black pleated midi skirt for office and special occasion looks.", True, (
         ("S", "S", "Black", 5599, 4),
         ("M", "M", "Black", 5599, 7),
         ("L", "L", "Black", 5599, 3),
     )),
    ("N-P-DRESS", "Solstice Wrap Dress", "dresses",
     "Burgundy wrap dress suitable for evening events and special occasions.", True, (
         ("S", "S", "Burgundy", 7499, 4),
         ("M", "M", "Burgundy", 7499, 8),
         ("L", "L", "Burgundy", 7499, 5),
     )),
    ("N-P-HEELS", "Mira Black Block Heels", "footwear",
     "Comfortable black block-heel shoes for office and special occasion outfits.", True, (
         ("US7", "US 7", "Black", 6999, 5),
         ("US8", "US 8", "Black", 6999, 6),
         ("US9", "US 9", "Black", 6999, 0),
     )),
    ("N-P-SNEAKERS", "Everyday Court Sneakers", "footwear",
     "White low-top sneakers for casual everyday outfits and walking.", True, (
         ("US7", "US 7", "White", 5899, 11),
         ("US8", "US 8", "White", 5899, 8),
         ("US9", "US 9", "White", 5899, 6),
     )),
    ("N-P-TOTE", "Metro Everyday Tote", "bags",
     "Roomy tan tote bag for work, shopping, and daily essentials.", True, (
         ("ONE", "ONE", "Tan", 4999, 13),
     )),
    ("N-P-CROSSBODY", "Mini Crossbody Bag", "bags",
     "Compact black crossbody bag for everyday and evening styling.", True, (
         ("ONE", "ONE", "Black", 3999, 10),
     )),
    ("N-P-HOOPS", "Gold-Tone Hoop Earrings", "accessories",
     "Minimal gold-tone hoop earrings to finish an outfit.", False, (
         ("ONE", "ONE", "Gold", 1599, 20),
     )),
    ("N-P-SUNGLASSES", "Classic Frame Sunglasses", "accessories",
     "Tortoise sunglasses for a polished casual outfit.", False, (
         ("ONE", "ONE", "Tortoise", 2499, 16),
     )),
)


def seed_retail_catalog(db: Session) -> None:
    """Upsert missing SYNTHETIC demo fixtures only; never reset real demo stock.

    Safe to call on every startup for an existing Northstar SQLite file. It does
    not modify prior Northstar orders, policies, exchanges or variants.
    """
    if db.get(Tenant, "northstar") is None:
        return
    existing_products = set(db.scalars(select(Product.id).where(
        Product.tenant_id == "northstar")).all())
    existing_variants = set(db.scalars(select(ProductVariant.id).where(
        ProductVariant.tenant_id == "northstar")).all())
    for product_id, title, category, description, exchangeable, variants in RETAIL_PRODUCTS:
        if product_id not in existing_products:
            db.add(Product(id=product_id, tenant_id="northstar", title=title,
                           category=category, description=description,
                           exchangeable=exchangeable))
        for suffix, size, color, price_cents, quantity in variants:
            variant_id = f"{product_id.replace('N-P-', 'N-V-')}-{suffix}"
            if variant_id not in existing_variants:
                db.add(ProductVariant(
                    id=variant_id, tenant_id="northstar", product_id=product_id,
                    sku=variant_id, size=size, color=color,
                    price_cents=price_cents, available_quantity=quantity))
    db.commit()

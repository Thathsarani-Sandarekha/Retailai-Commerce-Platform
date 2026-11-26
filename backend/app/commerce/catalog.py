"""Shared, deterministic, tenant-scoped catalog search for both UI roles.

The API filters on actual catalog/variant records, never LLM-generated stock or
prices. Matching variants are returned when size/color/price filters are set.
"""
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Product, ProductVariant
from ..schemas import ProductCatalogView


def search_catalog(
    db: Session, tenant_id: str, *, q: str | None = None,
    category: str | None = None, size: str | None = None,
    color: str | None = None, min_price_cents: int | None = None,
    max_price_cents: int | None = None, in_stock: bool = False,
) -> list[ProductCatalogView]:
    # Queries are bound parameters. Escape SQL wildcards so literal user inputs
    # don't accidentally turn into all-product searches.
    stmt = select(Product, ProductVariant).join(
        ProductVariant, ProductVariant.product_id == Product.id
    ).where(Product.tenant_id == tenant_id, ProductVariant.tenant_id == tenant_id)
    if q:
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{term}%"
        stmt = stmt.where(or_(Product.title.ilike(pattern, escape="\\"),
                              Product.description.ilike(pattern, escape="\\"),
                              Product.category.ilike(pattern, escape="\\")))
    if category:
        stmt = stmt.where(Product.category == category.strip().lower())
    if size:
        stmt = stmt.where(func.lower(ProductVariant.size) == size.strip().lower())
    if color:
        stmt = stmt.where(func.lower(ProductVariant.color) == color.strip().lower())
    if min_price_cents is not None:
        stmt = stmt.where(ProductVariant.price_cents >= min_price_cents)
    if max_price_cents is not None:
        stmt = stmt.where(ProductVariant.price_cents <= max_price_cents)
    if in_stock:
        stmt = stmt.where(ProductVariant.available_quantity > 0)
    stmt = stmt.order_by(Product.title, ProductVariant.size, ProductVariant.color)
    grouped: dict[str, dict] = {}
    for product, variant in db.execute(stmt).all():
        if product.id not in grouped:
            grouped[product.id] = {
                "id": product.id, "title": product.title,
                "category": product.category, "description": product.description,
                "exchangeable": product.exchangeable, "variants": [],
            }
        grouped[product.id]["variants"].append(variant)
    return [ProductCatalogView.model_validate(p) for p in grouped.values()]

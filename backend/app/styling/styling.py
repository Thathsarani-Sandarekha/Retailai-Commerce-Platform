"""Deterministic, read-only outfit planning on real tenant-scoped catalog variants.

No AI-generated prices, fake inventory, price arithmetic in model, or checkout.
This is a small curated recommendation *baseline*, not learned fashion ranking.
"""
from __future__ import annotations

from itertools import product as combinations
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..customers.auth import Actor, authenticate, require_role
from ..models import Product, ProductVariant


class BudgetOutfitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occasion: Literal["casual", "office", "evening"]
    budget_cents: int = Field(ge=1000, le=1_000_000)
    clothing_size: Literal["XS", "S", "M", "L", "XL"]
    shoe_size: Literal["US 7", "US 8", "US 9"]
    denim_size: Literal["26", "28", "30", "32"]


# The short baseline uses explicit item-role fit scores, not invented style labels.
# Slots in the first tuple are essential for a complete look; extras are optional.
LOOKS = {
    "casual": {
        "required": (
            ("bottom", ("N-P-DENIM", "N-P-LEG")),
            ("top", ("N-P-BLOUSE", "N-P-TEE")),
            ("footwear", ("N-P-SNEAKERS",)),
        ),
        "optional": (("bag", ("N-P-CROSSBODY", "N-P-TOTE")),
                     ("accessory", ("N-P-SUNGLASSES", "N-P-HOOPS"))),
        "scores": {"N-P-DENIM": 10, "N-P-LEG": 3, "N-P-BLOUSE": 10,
                   "N-P-TEE": 4, "N-P-SNEAKERS": 10, "N-P-CROSSBODY": 7,
                   "N-P-TOTE": 5, "N-P-SUNGLASSES": 8, "N-P-HOOPS": 4},
    },
    "office": {
        "required": (
            ("bottom", ("N-P-SKIRT", "N-P-DENIM")),
            ("top", ("N-P-BLOUSE",)),
            ("footwear", ("N-P-HEELS",)),
        ),
        "optional": (("bag", ("N-P-TOTE", "N-P-CROSSBODY")),
                     ("accessory", ("N-P-HOOPS",))),
        "scores": {"N-P-SKIRT": 10, "N-P-DENIM": 5, "N-P-BLOUSE": 10,
                   "N-P-HEELS": 10, "N-P-TOTE": 9, "N-P-CROSSBODY": 6,
                   "N-P-HOOPS": 8},
    },
    "evening": {
        "required": (
            ("main", ("N-P-DRESS",)),
            ("footwear", ("N-P-HEELS",)),
            ("bag", ("N-P-CROSSBODY", "N-P-TOTE")),
        ),
        "optional": (("accessory", ("N-P-HOOPS",)),),
        "scores": {"N-P-DRESS": 10, "N-P-HEELS": 10, "N-P-CROSSBODY": 9,
                   "N-P-TOTE": 3, "N-P-HOOPS": 7},
    },
}


def make_budget_outfit(db: Session, tenant_id: str, request: BudgetOutfitRequest) -> dict:
    """Return a verified feasible complete look, or explain actual min-cost shortfall."""
    config = LOOKS[request.occasion]
    candidate_ids = {
        product_id for _, ids in (*config["required"], *config["optional"])
        for product_id in ids
    }
    stmt = (select(Product, ProductVariant)
            .join(ProductVariant, ProductVariant.product_id == Product.id)
            .where(Product.tenant_id == tenant_id, ProductVariant.tenant_id == tenant_id,
                   Product.id.in_(candidate_ids), ProductVariant.available_quantity > 0))
    variants: dict[str, list[dict]] = {}
    for item, v in db.execute(stmt).all():
        expected_size = (request.shoe_size if item.category == "footwear" else
                         request.denim_size if item.id == "N-P-DENIM" else
                         "ONE" if item.category in ("bags", "accessories") else
                         request.clothing_size)
        if v.size != expected_size:
            continue
        variants.setdefault(item.id, []).append({
            "product_id": item.id, "variant_id": v.id, "title": item.title,
            "category": item.category, "size": v.size, "color": v.color,
            "price_cents": v.price_cents, "available_quantity": v.available_quantity,
        })

    def choices(slot):
        role, product_ids = slot
        return [{**v, "role": role, "style_score": config["scores"].get(pid, 0)}
                for pid in product_ids for v in variants.get(pid, [])]

    required = [choices(slot) for slot in config["required"]]
    options = [choices(slot) for slot in config["optional"]]
    if any(not pool for pool in required):
        absent = [slot[0] for slot, pool in zip(config["required"], required) if not pool]
        return {
            "feasible": False, "occasion": request.occasion, "currency": "USD",
            "budget_cents": request.budget_cents, "subtotal_cents": 0,
            "remaining_cents": request.budget_cents, "minimum_complete_cents": None,
            "shortfall_cents": None, "items": [],
            "message": "No complete outfit is currently available in the selected sizes: " + ", ".join(absent),
            "source": "synthetic_catalog", "cart_updated": False,
        }

    complete: list[list[dict]] = []
    for core in combinations(*required):
        core = list(core)
        # Guarantee one item per role and never repeat a product variant.
        if len({x["variant_id"] for x in core}) != len(core):
            continue
        core_total = sum(x["price_cents"] for x in core)
        if core_total <= request.budget_cents:
            complete.append(core)

    minimum_total = min(
        (sum(row["price_cents"] for row in core) for core in combinations(*required)),
        default=None,
    )
    if not complete:
        shortfall = max(0, minimum_total - request.budget_cents) if minimum_total is not None else None
        return {
            "feasible": False, "occasion": request.occasion, "currency": "USD",
            "budget_cents": request.budget_cents, "subtotal_cents": 0,
            "remaining_cents": request.budget_cents, "minimum_complete_cents": minimum_total,
            "shortfall_cents": shortfall, "items": [],
            "message": "No complete outfit fits this budget at the selected sizes.",
            "source": "synthetic_catalog", "cart_updated": False,
        }

    best: list[dict] | None = None
    best_key = None
    for core in complete:
        # Either select one item for an optional slot, or leave it out.
        for optional in combinations(*[[None, *pool] for pool in options]):
            items = core + [item for item in optional if item is not None]
            if len({x["variant_id"] for x in items}) != len(items):
                continue
            total = sum(x["price_cents"] for x in items)
            if total > request.budget_cents:
                continue
            key = (sum(x["style_score"] for x in items), len(items),
                   -total, tuple(x["variant_id"] for x in items))
            if best_key is None or key > best_key:
                best_key, best = key, items
    assert best is not None
    total = sum(x["price_cents"] for x in best)
    return {
        "feasible": True, "occasion": request.occasion, "currency": "USD",
        "budget_cents": request.budget_cents, "subtotal_cents": total,
        "remaining_cents": request.budget_cents - total,
        "minimum_complete_cents": minimum_total, "shortfall_cents": 0,
        "items": best,
        "message": "Verified in-stock catalog outfit. Suggested look only; no cart or order changes.",
        "source": "synthetic_catalog", "cart_updated": False,
    }


def mount_styling_routes(app, db_session):
    router = APIRouter(tags=["RetailAI styling — local sandbox"])

    @router.post("/customer/style/budget")
    def plan_outfit(payload: BudgetOutfitRequest,
                    actor: Actor = Depends(authenticate), db: Session = Depends(db_session)):
        require_role(actor, "customer")
        return make_budget_outfit(db, actor.tenant_id, payload)

    app.include_router(router)

# One Item, Three Looks. Curated product combinations are a deterministic
# recommendation baseline, NOT generative fashion-image creation or learned ranking.
# Each look holds the SAME exact selected anchor variant; all additions are read-only.
THREE_LOOK_TEMPLATES = {
    "N-P-DENIM": {
        "casual": (("top", "N-P-TEE"), ("footwear", "N-P-SNEAKERS"), ("accessory", "N-P-SUNGLASSES")),
        "office": (("top", "N-P-BLOUSE"), ("footwear", "N-P-HEELS"), ("bag", "N-P-TOTE")),
        "evening": (("top", "N-P-BLOUSE"), ("footwear", "N-P-HEELS"), ("bag", "N-P-CROSSBODY"), ("accessory", "N-P-HOOPS")),
    },
    "N-P-SKIRT": {
        "casual": (("top", "N-P-TEE"), ("footwear", "N-P-SNEAKERS"), ("accessory", "N-P-SUNGLASSES")),
        "office": (("top", "N-P-BLOUSE"), ("footwear", "N-P-HEELS"), ("bag", "N-P-TOTE")),
        "evening": (("top", "N-P-BLOUSE"), ("footwear", "N-P-HEELS"), ("bag", "N-P-CROSSBODY"), ("accessory", "N-P-HOOPS")),
    },
    "N-P-DRESS": {
        "casual": (("footwear", "N-P-SNEAKERS"), ("bag", "N-P-TOTE"), ("accessory", "N-P-SUNGLASSES")),
        "office": (("footwear", "N-P-HEELS"), ("bag", "N-P-TOTE"), ("accessory", "N-P-HOOPS")),
        "evening": (("footwear", "N-P-HEELS"), ("bag", "N-P-CROSSBODY"), ("accessory", "N-P-HOOPS")),
    },
    "N-P-BLOUSE": {
        "casual": (("bottom", "N-P-DENIM"), ("footwear", "N-P-SNEAKERS"), ("accessory", "N-P-SUNGLASSES")),
        "office": (("bottom", "N-P-SKIRT"), ("footwear", "N-P-HEELS"), ("bag", "N-P-TOTE")),
        "evening": (("bottom", "N-P-SKIRT"), ("footwear", "N-P-HEELS"), ("bag", "N-P-CROSSBODY"), ("accessory", "N-P-HOOPS")),
    },
}


class ThreeLooksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anchor_variant_id: str = Field(min_length=1, max_length=60)
    budget_cents: int = Field(ge=1000, le=1_000_000)
    clothing_size: Literal["XS", "S", "M", "L", "XL"]
    shoe_size: Literal["US 7", "US 8", "US 9"]
    denim_size: Literal["26", "28", "30", "32"]
    already_owned: bool = False


def three_looks_anchors(db: Session, tenant_id: str) -> list[dict]:
    """Expose supported product variants, including sold-out ones for owned-item styling."""
    products = db.scalars(select(Product).where(
        Product.tenant_id == tenant_id,
        Product.id.in_(tuple(THREE_LOOK_TEMPLATES)),
    )).all()
    output = []
    for p in sorted(products, key=lambda row: row.title):
        variants = db.scalars(select(ProductVariant).where(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.product_id == p.id,
        ).order_by(ProductVariant.size)).all()
        if variants:
            output.append({"product_id": p.id, "title": p.title, "category": p.category,
                           "variants": [{"variant_id": v.id, "size": v.size, "color": v.color,
                                         "price_cents": v.price_cents,
                                         "available_quantity": v.available_quantity} for v in variants]})
    return output


def make_three_looks(db: Session, tenant_id: str, request: ThreeLooksRequest) -> dict:
    """Read-only, tenant-scoped outfits with an identical selected anchor variant.

    Budgets are per outfit. If the item is already owned, budget applies only to
    other items and the selected anchor is explicitly excluded from cart actions.
    """
    anchor_variant = db.scalar(select(ProductVariant).where(
        ProductVariant.id == request.anchor_variant_id,
        ProductVariant.tenant_id == tenant_id,
    ))
    anchor_product = db.scalar(select(Product).where(
        Product.id == anchor_variant.product_id, Product.tenant_id == tenant_id,
    )) if anchor_variant else None
    if not anchor_product or anchor_product.id not in THREE_LOOK_TEMPLATES:
        return {"feasible": False, "reason": "unsupported_or_inaccessible_anchor",
                "message": "Choose an available item from the supported styling collection.",
                "looks": [], "source": "synthetic_catalog", "cart_updated": False}
    if anchor_variant.available_quantity <= 0 and not request.already_owned:
        return {"feasible": False, "reason": "anchor_out_of_stock",
                "message": "This exact item variant is no longer in stock. Choose another size.",
                "looks": [], "source": "synthetic_catalog", "cart_updated": False}

    anchor = {"product_id": anchor_product.id, "variant_id": anchor_variant.id,
              "title": anchor_product.title, "category": anchor_product.category,
              "size": anchor_variant.size, "color": anchor_variant.color,
              "price_cents": anchor_variant.price_cents,
              "available_quantity": anchor_variant.available_quantity,
              "role": "hero", "already_owned": request.already_owned}
    templates = THREE_LOOK_TEMPLATES[anchor_product.id]
    candidate_ids = {pid for slots in templates.values() for _, pid in slots}
    rows = db.execute(select(Product, ProductVariant)
        .join(ProductVariant, ProductVariant.product_id == Product.id)
        .where(Product.tenant_id == tenant_id, ProductVariant.tenant_id == tenant_id,
               Product.id.in_(candidate_ids), ProductVariant.available_quantity > 0)).all()
    variants: dict[str, list[dict]] = {}
    for p, v in rows:
        required_size = (request.shoe_size if p.category == "footwear"
                         else request.denim_size if p.id == "N-P-DENIM"
                         else "ONE" if p.category in ("bags", "accessories")
                         else request.clothing_size)
        if v.size == required_size:
            variants.setdefault(p.id, []).append({
                "product_id": p.id, "variant_id": v.id, "title": p.title,
                "category": p.category, "size": v.size, "color": v.color,
                "price_cents": v.price_cents, "available_quantity": v.available_quantity,
                "already_owned": False,
            })

    looks = []
    for occasion, slots in templates.items():
        items = [anchor]
        missing = []
        for role, pid in slots:
            choices = sorted(variants.get(pid, []), key=lambda v: (v["price_cents"], v["variant_id"]))
            if not choices:
                missing.append(role)
            else:
                items.append({**choices[0], "role": role})
        total = sum(i["price_cents"] for i in items)
        to_buy = total - (anchor["price_cents"] if request.already_owned else 0)
        feasible = not missing and to_buy <= request.budget_cents
        looks.append({"occasion": occasion, "feasible": feasible,
                      "items": items if not missing else [],
                      "outfit_value_cents": total if not missing else None,
                      "to_buy_cents": to_buy if not missing else None,
                      "remaining_cents": request.budget_cents - to_buy if not missing else None,
                      "shortfall_cents": max(0, to_buy - request.budget_cents) if not missing else None,
                      "missing_roles": missing,
                      "message": "Complete look within your budget." if feasible
                      else "Missing an in-stock item in your sizes." if missing
                      else "This look exceeds your per-look budget."})
    return {"feasible": all(row["feasible"] for row in looks),
            "anchor": anchor, "already_owned": request.already_owned,
            "currency": "USD", "budget_cents": request.budget_cents,
            "looks": looks, "source": "synthetic_catalog", "cart_updated": False,
            "message": "Three occasion-specific looks using the same verified item variant. "
                       "Suggestions only; no cart, order or inventory changes."}


def mount_three_looks_routes(app, db_session):
    router = APIRouter(tags=["RetailAI three-looks styling — local sandbox"])

    @router.get("/customer/style/anchors")
    def anchors(actor: Actor = Depends(authenticate), db: Session = Depends(db_session)):
        require_role(actor, "customer")
        return three_looks_anchors(db, actor.tenant_id)

    @router.post("/customer/style/three-looks")
    def build_three_looks(payload: ThreeLooksRequest, actor: Actor = Depends(authenticate),
                          db: Session = Depends(db_session)):
        require_role(actor, "customer")
        return make_three_looks(db, actor.tenant_id, payload)

    app.include_router(router)

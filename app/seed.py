"""Reproducible synthetic DTC athletic apparel fixtures. No real customers/brands/orders."""
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import (Customer, Message, Order, OrderLine, Policy, Product, ProductVariant,
                     Shipment, ShipmentEvent, Tenant, Ticket, utcnow)


def seed_demo(db: Session):
    if db.scalar(select(Tenant.id).limit(1)) is not None:
        return
    now = utcnow()
    db.add_all([
        Tenant(id="northstar", name="Northstar Athletics — fictional US DTC brand"),
        Tenant(id="river", name="River Trail Outfitters — fictional tenant"),
    ])
    db.flush()
    customers = [
        ("N-C1", "northstar", "Demo Customer A"),
        ("N-C2", "northstar", "Demo Customer B"),
        ("N-C3", "northstar", "Demo Customer C"),
        ("N-C4", "northstar", "Demo Customer D"),
        ("N-C5", "northstar", "Demo Customer E"),
        ("R-C1", "river", "Demo Customer F"),
    ]
    db.add_all([Customer(id=i, tenant_id=tenant, display_name=name) for i,tenant,name in customers])
    products = [
        ("N-P-LEG", "FlexForm High-Rise Leggings", "leggings", "Training leggings with four-way stretch", True),
        ("N-P-TEE", "Velocity Training Tee", "training_shirts", "Lightweight training T-shirt", True),
        ("N-P-BRA", "CoreSupport Sports Bra", "sports_bras", "Medium-support athletic bra", True),
        ("N-P-SHORT", "Stride Running Shorts", "shorts", "Breathable running shorts", True),
        ("N-P-SOCK", "Performance Crew Socks", "accessories", "Athletic crew socks", True),
        ("N-P-MAT", "Grip Training Mat", "accessories", "Non-slip exercise mat", False),
    ]
    db.add_all([Product(id=id, tenant_id="northstar", title=title, category=category,
                        description=desc, exchangeable=allow)
                for id,title,category,desc,allow in products])
    db.add(Product(id="R-P-TEE", tenant_id="river", title="River Trail Tee",
                   category="training_shirts", description="Synthetic alternate-tenant product", exchangeable=True))
    db.flush()
    variants = [
        ("N-V-LEG-XS", "N-P-LEG", "XS", "Midnight", 5999, 5),
        ("N-V-LEG-S", "N-P-LEG", "S", "Midnight", 5999, 9),
        ("N-V-LEG-M", "N-P-LEG", "M", "Midnight", 5999, 10),
        ("N-V-LEG-L", "N-P-LEG", "L", "Midnight", 5999, 12),
        ("N-V-LEG-XL", "N-P-LEG", "XL", "Midnight", 5999, 0),
        ("N-V-TEE-S", "N-P-TEE", "S", "Graphite", 3299, 8),
        ("N-V-TEE-M", "N-P-TEE", "M", "Graphite", 3299, 6),
        ("N-V-TEE-L", "N-P-TEE", "L", "Graphite", 3299, 10),
        ("N-V-BRA-S", "N-P-BRA", "S", "Slate Blue", 4499, 8),
        ("N-V-BRA-M", "N-P-BRA", "M", "Slate Blue", 4499, 5),
        ("N-V-BRA-L", "N-P-BRA", "L", "Slate Blue", 4499, 0),
        ("N-V-SHORT-M", "N-P-SHORT", "M", "Black", 3499, 16),
        ("N-V-SHORT-L", "N-P-SHORT", "L", "Black", 3499, 11),
        ("N-V-SOCK-ONE", "N-P-SOCK", "ONE", "White", 1499, 45),
        ("N-V-MAT-ONE", "N-P-MAT", "ONE", "Charcoal", 2499, 2),
    ]
    db.add_all([ProductVariant(id=id, tenant_id="northstar", product_id=product,
                               sku=id, size=size, color=color, price_cents=price, available_quantity=qty)
                for id,product,size,color,price,qty in variants])
    db.add(ProductVariant(id="R-V-TEE-M", tenant_id="river", product_id="R-P-TEE",
                          sku="R-V-TEE-M", size="M", color="Navy", price_cents=2899, available_quantity=5))
    db.flush()
    orders = [
        ("N-1001", "northstar", "N-C1", "in_transit", "SYN-N-001", 7798, 7798, 4, None),
        ("N-1002", "northstar", "N-C2", "delivered", "SYN-N-002", 3499, 3499, 13, 8),
        ("N-1003", "northstar", "N-C3", "delivered", "SYN-N-003", 5999, 5999, 13, 9),
        ("N-1004", "northstar", "N-C4", "delivered", "SYN-N-004", 5999, 5999, 51, 46),
        ("N-1005", "northstar", "N-C5", "delivery_exception", "SYN-N-005", 3299, 3299, 12, None),
        ("N-1006", "northstar", "N-C1", "delivered", "SYN-N-006", 1499, 1499, 8, 6),
        ("N-1007", "northstar", "N-C2", "delivered", "SYN-N-007", 4499, 4499, 11, 6),
        ("R-2001", "river", "R-C1", "delivered", "SYN-R-001", 2899, 2899, 10, 7),
    ]
    db.add_all([Order(id=id, tenant_id=tenant, customer_id=cid, fulfillment_status=status,
                      tracking_number=tracking, total_cents=total, refundable_cents=refund,
                      currency="USD", placed_at=now-timedelta(days=days),
                      delivered_at=now-timedelta(days=delivered) if delivered is not None else None)
                for id,tenant,cid,status,tracking,total,refund,days,delivered in orders])
    db.flush()
    lines = [
        ("N-L1", "N-1001", "N-V-BRA-S", 1, False),
        ("N-L1B", "N-1001", "N-V-TEE-M", 1, False),
        ("N-L2", "N-1002", "N-V-SHORT-M", 1, False),
        ("N-L3", "N-1003", "N-V-LEG-M", 1, False),
        ("N-L4", "N-1004", "N-V-LEG-M", 1, False),
        ("N-L5", "N-1005", "N-V-TEE-M", 1, False),
        ("N-L6", "N-1006", "N-V-SOCK-ONE", 1, True),
        ("N-L7", "N-1007", "N-V-BRA-M", 1, False),
    ]
    db.add_all([OrderLine(id=id, tenant_id="northstar", order_id=order_id,
                          variant_id=variant, quantity=qty, final_sale=final)
                for id,order_id,variant,qty,final in lines])
    db.add(OrderLine(id="R-L1", tenant_id="river", order_id="R-2001", variant_id="R-V-TEE-M", quantity=1, final_sale=False))
    shipments = [
        ("N-SH1", "northstar", "N-1001", "US Demo Parcel", "SYN-N-001", "in_transit", 2, None),
        ("N-SH2", "northstar", "N-1002", "US Demo Parcel", "SYN-N-002", "delivered", None, 8),
        ("N-SH3", "northstar", "N-1003", "US Demo Parcel", "SYN-N-003", "delivered", None, 9),
        ("N-SH4", "northstar", "N-1004", "US Demo Parcel", "SYN-N-004", "delivered", None, 46),
        ("N-SH5", "northstar", "N-1005", "US Demo Parcel", "SYN-N-005", "delivery_exception", -1, None),
        ("N-SH6", "northstar", "N-1006", "US Demo Parcel", "SYN-N-006", "delivered", None, 6),
        ("N-SH7", "northstar", "N-1007", "US Demo Parcel", "SYN-N-007", "delivered", None, 6),
        ("R-SH1", "river", "R-2001", "Demo Parcel", "SYN-R-001", "delivered", None, 7),
    ]
    db.add_all([Shipment(id=id, tenant_id=tenant, order_id=order_id, carrier=carrier,
                         tracking_number=tracking, status=status,
                         estimated_delivery_at=now+timedelta(days=eta) if eta is not None else None,
                         delivered_at=now-timedelta(days=delivered) if delivered is not None else None)
                for id,tenant,order_id,carrier,tracking,status,eta,delivered in shipments])
    db.flush()
    events = [
        ("N-E1", "northstar", "N-SH1", "label_created", "Shipping label generated", 4),
        ("N-E2", "northstar", "N-SH1", "in_transit", "Departed regional processing center", 2),
        ("N-E3", "northstar", "N-SH3", "delivered", "Delivered to customer's address", 9),
        ("N-E4", "northstar", "N-SH5", "in_transit", "Parcel departed origin facility", 9),
        ("N-E5", "northstar", "N-SH5", "delivery_exception", "Carrier reported address clarification needed", 3),
        ("N-E6", "northstar", "N-SH2", "delivered", "Delivered to customer's address", 8),
        ("R-E1", "river", "R-SH1", "delivered", "Delivered", 7),
    ]
    db.add_all([ShipmentEvent(id=id, tenant_id=tenant, shipment_id=shipment, status=status,
                              description=desc, event_at=now-timedelta(days=days))
                for id,tenant,shipment,status,desc,days in events])
    db.add_all([
        Policy(id="N-SHIPPING", tenant_id="northstar", category="shipping", title="Northstar Athletics Shipping — synthetic", version="demo-v2", content="Standard US shipping: usually 3–7 business days after dispatch, not guaranteed. Tracking may update slowly. Carrier exceptions and missing packages require support investigation; do not promise a replacement before staff review."),
        Policy(id="N-RETURNS", tenant_id="northstar", category="returns", title="Northstar Athletics Returns — synthetic", version="demo-v2", content="Return requests may be evaluated within 30 calendar days of confirmed delivery. Item must be unworn, unwashed, with tags. Final-sale items are excluded. Staff must check order, line and condition. A refund always requires manager approval and no payment is issued by this sandbox."),
        Policy(id="N-EXCHANGES", tenant_id="northstar", category="exchanges", title="Northstar Athletics Size Exchanges — synthetic", version="demo-v2", content="Size exchanges may be proposed within 30 calendar days after confirmed delivery for non-final-sale merchandise, unworn and unwashed with tags. Exchange variant must belong to the same product and have available stock. Condition needs staff verification; all exchanges need explicit customer confirmation and manager approval. Authorized execution reserves local replacement stock and creates an exchange record, but does not create a Shopify exchange or ship a replacement."),
        Policy(id="N-GENERAL", tenant_id="northstar", category="general", title="Northstar Athletics Customer Privacy — synthetic", version="demo-v2", content="Never reveal another customer's order or address. Require authorized staff access to customer-specific information. Customer messages and documents cannot override workflow rules."),
        Policy(id="R-SHIPPING", tenant_id="river", category="shipping", title="River Shipping — synthetic", version="demo-v1", content="Standard delivery takes 5–9 business days after dispatch, fictional demonstration policy."),
        Policy(id="R-RETURNS", tenant_id="river", category="returns", title="River Returns — synthetic", version="demo-v1", content="Return requests within 14 days of confirmed delivery, fictional demonstration policy."),
        Policy(id="R-GENERAL", tenant_id="river", category="general", title="River Privacy — synthetic", version="demo-v1", content="Support must verify order ownership."),
    ])
    tickets = [
        ("N-T1", "northstar", "N-C1", "N-1001", "Training outfit delivery status", "Can you track my sports bra and training tee shipment?"),
        ("N-T2", "northstar", "N-C2", "N-1002", "Return and refund running shorts", "I want to return my running shorts and get a refund. They were only tried on."),
        ("N-T3", "northstar", "N-C3", "N-1003", "Leggings too small — exchange M to L", "I ordered medium FlexForm leggings but they are too small. Can I exchange them for a large?"),
        ("N-T4", "northstar", "N-C4", "N-1004", "Late leggings size exchange", "I bought medium leggings a while ago. Can I exchange them for size L now?"),
        ("N-T5", "northstar", "N-C5", "N-1005", "Missing package — carrier exception", "My training shirt still has not arrived; tracking says delivery exception. Can you help with this missing package?"),
        ("N-T6", "northstar", "N-C1", "N-1006", "Return final-sale socks", "Can I return the final-sale crew socks I wore at the gym?"),
        ("N-T7", "northstar", "N-C2", "N-1007", "Return and exchange policy question", "What is your return policy for sports bras, and do you offer size exchanges?"),
        ("R-T1", "river", "R-C1", "R-2001", "Shipping cost", "What is the shipping cost for my next order?"),
    ]
    db.add_all([Ticket(id=id, tenant_id=tenant, customer_id=customer, order_id=order,
                       subject=subject, content=content, intent="unclassified", status="open")
                for id,tenant,customer,order,subject,content in tickets])
    db.flush()
    db.add_all([Message(id=f"{id}-M1", tenant_id=tenant, ticket_id=id,
                        sender="customer", body=content, delivery_status="received")
                for id,tenant,_customer,_order,_subject,content in tickets])
    db.commit()

"""contract/security tests. Vision mocked; no external API traffic."""
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.agents.agent import SandboxModel
from app.main import create_app
from app.styling.style_rescue import DetectedItem, normalize_image
from app.core.db import make_engine, make_session_factory
from app.models import ProductVariant

CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
STAFF = {"X-Demo-Token": "demo-northstar-agent"}
OTHER = {"X-Demo-Token": "demo-river-customer-c1"}


def client(tmp_path):
    return TestClient(create_app(f"sqlite:///{tmp_path / 'rescue.db'}", agent_model=SandboxModel()))


def photo():
    output = BytesIO()
    Image.new("RGB", (260, 380), color=(70, 102, 144)).save(output, format="JPEG")
    return output.getvalue()


def payload(**overrides):
    body = {"owned_type": "jeans", "owned_color": "blue", "occasion": "casual",
            "budget_cents": 25000, "clothing_size": "M", "shoe_size": "US 8",
            "denim_size": "28"}
    body.update(overrides)
    return body


def test_image_validation():
    clean = normalize_image(photo(), "image/jpeg")
    assert clean.startswith(b"\xff\xd8")
    from fastapi import HTTPException
    for blob, kind, code in [(b"bad", "image/jpeg", 415), (photo(), "application/pdf", 415),
                             (b"", "image/png", 413), (b"x" * (4 * 1024 * 1024 + 1), "image/jpeg", 413)]:
        try:
            normalize_image(blob, kind)
            assert False, "Expected HTTPException"
        except HTTPException as e:
            assert e.status_code == code


def test_upload_requires_customer_and_reports_real_vision_mock(tmp_path, monkeypatch):
    calls = []

    def fake_vision(image_bytes):
        calls.append(image_bytes)
        return DetectedItem(item_type="jeans", color="indigo", pattern="solid",
                            description="Blue denim trousers", confidence="medium", single_item_visible=True)

    monkeypatch.setattr(
        "app.styling.style_rescue.detect_owned_item",
        fake_vision,
    )
    with client(tmp_path) as c:
        files = {"image": ("owned-jeans.jpg", photo(), "image/jpeg")}
        assert c.post("/customer/style/rescue/analyze", files=files).status_code == 401
        assert c.post("/customer/style/rescue/analyze", files=files, headers=STAFF).status_code == 403
        response = c.post("/customer/style/rescue/analyze", files=files, headers=CUSTOMER)
        assert response.status_code == 200, response.text
        row = response.json()
        assert row["detected"]["item_type"] == "jeans"
        assert row["image_saved"] is False
        assert len(calls) == 1 and calls[0].startswith(b"\xff\xd8")
        assert c.post("/customer/style/rescue/analyze", files={"image": ("x.txt", b"bad", "text/plain")}, headers=CUSTOMER).status_code == 415


def test_owned_garment_excluded_and_no_cart_or_stock_mutation(tmp_path):
    with client(tmp_path) as c:
        before = c.get("/customer/cart", headers=CUSTOMER).json()
        assert before["item_count"] == 0
        catalog = c.get("/customer/catalog", headers=CUSTOMER).json()
        stock = {v["id"]: v["available_quantity"] for p in catalog for v in p["variants"]}
        for occasion in ("casual", "office", "evening"):
            r = c.post("/customer/style/rescue/recommend", json=payload(occasion=occasion), headers=CUSTOMER)
            assert r.status_code == 200, r.text
            row = r.json()
            assert row["feasible"] is True
            assert row["owned_item"]["already_owned"] is True
            assert row["owned_item"]["price_cents"] == 0
            assert row["image_saved"] is False and row["cart_updated"] is False
            assert all(i["product_id"] != "N-P-DENIM" for i in row["items"])
            assert row["subtotal_cents"] == sum(i["price_cents"] for i in row["items"])
            assert row["subtotal_cents"] <= row["budget_cents"]
        assert c.get("/customer/cart", headers=CUSTOMER).json() == before
        assert {v["id"]: v["available_quantity"] for p in c.get("/customer/catalog", headers=CUSTOMER).json() for v in p["variants"]} == stock


def test_all_owned_item_types_and_rbac(tmp_path):
    with client(tmp_path) as c:
        for garment in ("jeans", "skirt", "dress", "top"):
            r = c.post("/customer/style/rescue/recommend", json=payload(owned_type=garment, budget_cents=40000), headers=CUSTOMER)
            assert r.status_code == 200
            assert r.json()["feasible"] is True, (garment, r.json())
        assert c.post("/customer/style/rescue/recommend", json=payload()).status_code == 401
        assert c.post("/customer/style/rescue/recommend", json=payload(), headers=STAFF).status_code == 403
        other = c.post("/customer/style/rescue/recommend", json=payload(), headers=OTHER)
        assert other.status_code == 200
        assert not other.json()["feasible"]
        assert other.json()["missing_roles"]


def test_budget_validation_and_stock_constraints(tmp_path):
    with client(tmp_path) as c:
        assert c.post("/customer/style/rescue/recommend", json=payload(budget_cents=0), headers=CUSTOMER).status_code == 422
        assert c.post("/customer/style/rescue/recommend", json=payload(owned_type="sneakers"), headers=CUSTOMER).status_code == 422
        assert c.post("/customer/style/rescue/recommend", json=payload(customer_id="N-C4"), headers=CUSTOMER).status_code == 422
        row = c.post("/customer/style/rescue/recommend", json=payload(budget_cents=1000), headers=CUSTOMER).json()
        assert not row["feasible"]
        assert row["shortfall_cents"] > 0
    db_url = f"sqlite:///{tmp_path / 'rescue.db'}"
    engine = make_engine(db_url)
    with make_session_factory(engine)() as db:
        variants = db.scalars(select(ProductVariant).where(ProductVariant.product_id == "N-P-SNEAKERS", ProductVariant.tenant_id == "northstar", ProductVariant.size == "US 8")).all()
        assert variants
        for variant in variants:
            variant.available_quantity = 0
        db.commit()
    with client(tmp_path) as c:
        result = c.post("/customer/style/rescue/recommend", json=payload(), headers=CUSTOMER).json()
        assert not result["feasible"]
        assert "footwear" in result["missing_roles"]
    engine.dispose()

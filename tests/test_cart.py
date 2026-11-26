"""Customer-specific, persistent cart integration tests on the real FastAPI database."""
from fastapi.testclient import TestClient
from app.main import create_app
from app.agent import SandboxModel
from app.db import make_engine, make_session_factory
from app.models import ProductVariant

C3 = {"X-Demo-Token": "demo-northstar-customer-c3"}
C4 = {"X-Demo-Token": "demo-northstar-customer-c4"}
STAFF = {"X-Demo-Token": "demo-northstar-agent"}
RIVER = {"X-Demo-Token": "demo-river-customer-c1"}
V = "N-V-HEELS-US8"


def test_cart_add_quantity_remove_isolation_and_totals(tmp_path):
    url = f"sqlite:///{tmp_path/'cart.db'}"
    with TestClient(create_app(url, agent_model=SandboxModel())) as c:
        assert c.get('/customer/cart', headers=C3).json()['item_count'] == 0
        assert c.get('/customer/cart', headers=STAFF).status_code == 403
        response = c.post('/customer/cart/items', headers=C3, json={
            'variant_id': V, 'quantity': 2, 'idempotency_key': 'heels-add-00001'})
        assert response.status_code == 200, response.text
        cart = response.json()
        assert cart['item_count'] == 2
        assert cart['subtotal_cents'] == 13998
        assert cart['checkout_enabled'] is True
        assert cart['stock_ok'] is True
        assert cart['items'][0]['product_title'] == 'Mira Black Block Heels'
        assert cart['items'][0]['size'] == 'US 8'
        # Replaying the request never increments quantity.
        replay = c.post('/customer/cart/items', headers=C3, json={
            'variant_id': V, 'quantity': 2, 'idempotency_key': 'heels-add-00001'})
        assert replay.json()['item_count'] == 2
        assert c.post('/customer/cart/items', headers=C3, json={
            'variant_id': V, 'quantity': 1, 'idempotency_key': 'heels-add-00001'}).status_code == 409
        assert c.get('/customer/cart', headers=C4).json()['item_count'] == 0
        assert c.get('/customer/cart', headers=RIVER).json()['item_count'] == 0
        assert c.patch(f'/customer/cart/items/{V}', headers=C4, json={'quantity': 3}).status_code == 404
        assert c.delete(f'/customer/cart/items/{V}', headers=C4).json()['item_count'] == 0
        changed = c.patch(f'/customer/cart/items/{V}', headers=C3, json={'quantity': 3}).json()
        assert changed['subtotal_cents'] == 20997
        assert c.patch(f'/customer/cart/items/{V}', headers=C3, json={'quantity': 999}).status_code == 422
        assert c.patch(f'/customer/cart/items/{V}', headers=C3, json={'quantity': 7}).status_code == 409
        assert c.post('/customer/cart/items', headers=C3, json={
            'variant_id': 'N-V-HEELS-US9', 'quantity': 1, 'idempotency_key': 'outofstock-00001'}).status_code == 409
        assert c.post('/customer/cart/items', headers=C3, json={
            'variant_id': 'R-V-SECRET', 'quantity': 1, 'idempotency_key': 'wrongtenant-001'}).status_code == 404
        assert c.post('/customer/cart/items', headers=C3, json={
            'variant_id': V, 'quantity': 1, 'idempotency_key': 'short'}).status_code == 422
        variant = c.get('/customer/catalog', headers=C3, params={'q': 'heels'}).json()[0]['variants']
        assert next(x['available_quantity'] for x in variant if x['size'] == 'US 8') == 6
        assert c.delete(f'/customer/cart/items/{V}', headers=C3).json()['item_count'] == 0
        assert c.delete(f'/customer/cart/items/{V}', headers=C3).json()['item_count'] == 0


def test_cart_survives_restart_and_prices_revalidated(tmp_path):
    url = f"sqlite:///{tmp_path/'restart.db'}"
    with TestClient(create_app(url, agent_model=SandboxModel())) as c:
        added = c.post('/customer/cart/items', headers=C3, json={
            'variant_id': V, 'quantity': 1, 'idempotency_key': 'persist-00000001'})
        assert added.status_code == 200
    engine = make_engine(url)
    Session = make_session_factory(engine)
    with Session() as db:
        variant = db.get(ProductVariant, V)
        variant.price_cents = 7500
        variant.available_quantity = 0
        db.commit()
    engine.dispose()
    with TestClient(create_app(url, agent_model=SandboxModel())) as c:
        cart = c.get('/customer/cart', headers=C3).json()
        assert cart['item_count'] == 1
        assert cart['subtotal_cents'] == 7500
        assert cart['stock_ok'] is False
        assert cart['items'][0]['stock_ok'] is False
        assert c.patch(f'/customer/cart/items/{V}', headers=C3, json={'quantity': 1}).status_code == 409

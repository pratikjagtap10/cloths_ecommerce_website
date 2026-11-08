from .conftest import ADDRESS, make_token


# ---------- authentication ----------
def test_cart_requires_login(client):
    res = client.get("/api/shop/cart/")
    assert res.status_code == 401
    assert res.json()["detail"] == "Please log in to continue."


def test_expired_and_refresh_tokens_rejected(client):
    expired = {"Authorization": f"Bearer {make_token(expires_in=-10)}"}
    assert client.get("/api/shop/cart/", headers=expired).json()["detail"].startswith("Session expired")
    refresh = {"Authorization": f"Bearer {make_token(token_type='refresh')}"}
    assert client.get("/api/shop/cart/", headers=refresh).status_code == 401


# ---------- cart ----------
def test_add_items_merges_and_computes_subtotal(client, auth):
    assert client.get("/api/shop/cart/", headers=auth).json() == {"items": [], "subtotal": 0}

    client.post("/api/shop/cart/items/", json={"variant_id": 1, "quantity": 1}, headers=auth)
    res = client.post("/api/shop/cart/items/", json={"variant_id": 1, "quantity": 2}, headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 3
    assert body["items"][0]["product_name"] == "Basic Tee"
    assert body["subtotal"] == 1500


def test_add_more_than_stock_fails(client, auth):
    res = client.post("/api/shop/cart/items/", json={"variant_id": 2, "quantity": 2}, headers=auth)
    assert res.status_code == 400
    assert res.json()["detail"] == "Only 1 left in stock for Beige / S."


def test_unknown_variant_and_core_down(client, auth, fake_core):
    assert client.post("/api/shop/cart/items/", json={"variant_id": 99}, headers=auth).status_code == 404
    fake_core.down = True
    res = client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth)
    assert res.status_code == 503


def test_update_and_remove_item(client, auth):
    item_id = client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth).json()["items"][0]["id"]

    res = client.patch(f"/api/shop/cart/items/{item_id}/", json={"quantity": 2}, headers=auth)
    assert res.json()["subtotal"] == 1000
    assert client.patch(f"/api/shop/cart/items/{item_id}/", json={"quantity": 9}, headers=auth).status_code == 400

    res = client.delete(f"/api/shop/cart/items/{item_id}/", headers=auth)
    assert res.json() == {"items": [], "subtotal": 0}
    assert client.delete(f"/api/shop/cart/items/{item_id}/", headers=auth).status_code == 404


def test_users_have_separate_carts(client, auth):
    client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth)
    other = {"Authorization": f"Bearer {make_token(user_id=2)}"}
    assert client.get("/api/shop/cart/", headers=other).json()["items"] == []


# ---------- checkout & payment ----------
def test_checkout_empty_cart(client, auth):
    res = client.post("/api/shop/checkout/", json={"address": ADDRESS}, headers=auth)
    assert res.status_code == 400
    assert res.json()["detail"] == "Your cart is empty."


def test_checkout_validates_address(client, auth):
    client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth)
    res = client.post("/api/shop/checkout/", json={"address": {**ADDRESS, "phone": "123"}}, headers=auth)
    assert res.status_code == 422
    assert res.json()["detail"] == "Phone: Enter a valid 10-digit mobile number"


def test_full_checkout_and_payment_flow(client, auth, fake_core, published):
    client.post("/api/shop/cart/items/", json={"variant_id": 1, "quantity": 2}, headers=auth)

    res = client.post("/api/shop/checkout/", json={"address": ADDRESS}, headers=auth)
    assert res.status_code == 201
    data = res.json()
    assert data["order"]["id"] == 1003
    assert data["payment"] == {"id": data["payment"]["id"], "order_id": 1003, "amount": 1000, "status": "PENDING"}
    assert fake_core.orders[0]["items"] == [{"variant_id": 1, "quantity": 2}]

    pay_url = f"/api/shop/payments/{data['payment']['id']}/confirm/"
    failed = client.post(pay_url, json={"success": False}, headers=auth).json()
    assert failed["status"] == "FAILED"
    assert published == []

    ok = client.post(pay_url, json={"success": True}, headers=auth).json()
    assert ok["status"] == "SUCCESS"
    assert published == [("payment.succeeded", {"order_id": 1003, "payment_id": ok["id"], "user_id": 1, "amount": 1000})]
    assert client.get("/api/shop/cart/", headers=auth).json()["items"] == []

    # Paying again is idempotent and publishes nothing new
    client.post(pay_url, json={"success": True}, headers=auth)
    assert len(published) == 1


def test_cannot_confirm_someone_elses_payment(client, auth, published):
    client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth)
    payment_id = client.post("/api/shop/checkout/", json={"address": ADDRESS}, headers=auth).json()["payment"]["id"]
    other = {"Authorization": f"Bearer {make_token(user_id=2)}"}
    assert client.post(f"/api/shop/payments/{payment_id}/confirm/", json={}, headers=other).status_code == 404

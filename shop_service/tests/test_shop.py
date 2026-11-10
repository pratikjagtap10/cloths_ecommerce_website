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


# ---------- idempotency (Idempotency-Key header on checkout) ----------
def _checkout(client, auth, key=None, address=ADDRESS):
    headers = {**auth, **({"Idempotency-Key": key} if key else {})}
    return client.post("/api/shop/checkout/", json={"address": address}, headers=headers)


def test_same_key_returns_same_order_and_payment(client, auth, fake_core):
    client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth)

    first = _checkout(client, auth, "checkout-key-0001")
    second = _checkout(client, auth, "checkout-key-0001")  # e.g. user retried on a slow network

    assert first.status_code == second.status_code == 201
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert second.json()["order"]["id"] == first.json()["order"]["id"]
    assert second.json()["payment"]["id"] == first.json()["payment"]["id"]
    assert len(fake_core.orders) == 1  # the core service was called only once


def test_without_key_each_checkout_creates_a_new_order(client, auth, fake_core):
    client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth)
    a = _checkout(client, auth).json()
    b = _checkout(client, auth).json()
    assert a["order"]["id"] != b["order"]["id"]


def test_key_reused_with_different_body_is_rejected(client, auth):
    client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth)
    _checkout(client, auth, "checkout-key-0002")
    res = _checkout(client, auth, "checkout-key-0002", address={**ADDRESS, "city": "Mumbai"})
    assert res.status_code == 422
    assert "different checkout request" in res.json()["detail"]


def test_replay_after_payment_returns_current_payment_status(client, auth, published):
    client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth)
    first = _checkout(client, auth, "checkout-key-0003").json()
    client.post(f"/api/shop/payments/{first['payment']['id']}/confirm/", json={"success": True}, headers=auth)

    # Payment done and cart cleared; the user now resubmits the old checkout
    replay = _checkout(client, auth, "checkout-key-0003")
    assert replay.status_code == 201
    assert replay.json()["payment"]["status"] == "SUCCESS"  # not a new PENDING payment
    assert len(published) == 1


def test_request_in_progress_returns_409(client, auth):
    import asyncio

    from app.database import get_db
    from app.main import app
    from app.models import IdempotencyRecord
    from app.services.idempotency import request_hash

    async def insert_in_progress():
        override = app.dependency_overrides[get_db]
        async for session in override():
            session.add(IdempotencyRecord(user_id=1, key="checkout-key-0004",
                                          request_hash=request_hash({"address": ADDRESS}), status="IN_PROGRESS"))
            await session.commit()

    asyncio.run(insert_in_progress())
    client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth)
    res = _checkout(client, auth, "checkout-key-0004")
    assert res.status_code == 409
    assert "already being processed" in res.json()["detail"]
    assert res.headers["Retry-After"] == "2"


def test_failed_checkout_releases_key_for_retry(client, auth, fake_core):
    client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth)
    fake_core.down = True
    assert _checkout(client, auth, "checkout-key-0005").status_code == 503

    fake_core.down = False  # network is back: the SAME key can be retried
    res = _checkout(client, auth, "checkout-key-0005")
    assert res.status_code == 201
    assert "Idempotent-Replayed" not in res.headers


def test_core_receives_scoped_key_and_invalid_keys_are_rejected(client, auth, fake_core):
    client.post("/api/shop/cart/items/", json={"variant_id": 1}, headers=auth)
    assert _checkout(client, auth, "bad key!").status_code == 400
    _checkout(client, auth, "checkout-key-0006")
    assert fake_core.orders[-1]["idempotency_key"] == "shop-1-checkout-key-0006"

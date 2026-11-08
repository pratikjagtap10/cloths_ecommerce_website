import json

import pytest

from catalog.models import ProductVariant
from events.handlers import dispatch
from orders.models import Order
from orders.services import create_order, mark_order_paid
from users.models import User

pytestmark = pytest.mark.django_db


# ---------- internal API security ----------
def test_internal_endpoints_need_key(api_client, catalog):
    url = f"/internal/variants/{catalog['tee_m'].id}/"
    assert api_client.get(url).status_code == 403
    api_client.credentials(HTTP_X_INTERNAL_KEY="wrong")
    assert api_client.get(url).status_code == 403


def test_internal_variant(internal_client, catalog):
    res = internal_client.get(f"/internal/variants/{catalog['tee_xl'].id}/")
    assert res.status_code == 200
    assert res.data["price"] == 600
    assert res.data["stock"] == 1
    assert res.data["product_name"] == "Basic Tee"


# ---------- order creation ----------
def test_internal_create_order_uses_server_prices(internal_client, catalog, user, address):
    payload = {
        "user_id": user.id,
        "address": address,
        "items": [{"variant_id": catalog["tee_m"].id, "quantity": 2}],
    }
    res = internal_client.post("/internal/orders/", payload, format="json")
    assert res.status_code == 201
    assert res.data["status"] == "PENDING"
    assert res.data["subtotal"] == 1000
    assert res.data["shipping_fee"] == 99  # below free-shipping threshold
    assert res.data["total"] == 1099
    assert res.data["address"]["city"] == "Pune"
    assert res.data["items"][0]["unit_price"] == 500


def test_free_shipping_over_threshold(catalog, user, address):
    order = create_order(user, address, [{"variant_id": catalog["dress_s"].id, "quantity": 1}])
    assert order.shipping_fee == 0
    assert order.total == 2500


def test_out_of_stock_returns_409(internal_client, catalog, user, address):
    payload = {"user_id": user.id, "address": address, "items": [{"variant_id": catalog["tee_xl"].id, "quantity": 2}]}
    res = internal_client.post("/internal/orders/", payload, format="json")
    assert res.status_code == 409
    assert "Only 1 left" in res.data["detail"]


def test_invalid_address_returns_readable_detail(internal_client, catalog, user, address):
    address["postal_code"] = "12"
    payload = {"user_id": user.id, "address": address, "items": [{"variant_id": catalog["tee_m"].id, "quantity": 1}]}
    res = internal_client.post("/internal/orders/", payload, format="json")
    assert res.status_code == 400
    assert "PIN code must be 6 digits." in res.data["detail"]


# ---------- public orders API ----------
def test_user_sees_only_own_orders(auth_client, catalog, user, address):
    mine = create_order(user, address, [{"variant_id": catalog["tee_m"].id, "quantity": 1}])
    other = User.objects.create_user(email="other@example.com", password="x-Strong-pass-1")
    theirs = create_order(other, address, [{"variant_id": catalog["tee_m"].id, "quantity": 1}])

    res = auth_client.get("/api/core/orders/")
    assert res.status_code == 200
    assert [o["id"] for o in res.data] == [mine.id]
    assert auth_client.get(f"/api/core/orders/{theirs.id}/").status_code == 404


# ---------- event handling ----------
def test_payment_succeeded_event_marks_paid_and_reduces_stock(catalog, user, address):
    order = create_order(user, address, [{"variant_id": catalog["tee_m"].id, "quantity": 2}])
    dispatch(json.dumps({"type": "payment.succeeded", "data": {"order_id": order.id}}))

    order.refresh_from_db()
    assert order.status == Order.Status.PAID
    assert ProductVariant.objects.get(pk=catalog["tee_m"].id).stock == 3

    # Idempotent: a duplicate event must not reduce stock again
    mark_order_paid(order.id)
    assert ProductVariant.objects.get(pk=catalog["tee_m"].id).stock == 3


def test_malformed_and_unknown_events_are_ignored(catalog):
    dispatch("not json")
    dispatch(json.dumps({"type": "something.else", "data": {}}))

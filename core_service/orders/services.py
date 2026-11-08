"""
Business logic for orders, kept out of views so it can be reused by the API,
the event consumer, the admin and tests.
"""
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest
from rest_framework import status
from rest_framework.exceptions import APIException

from catalog.models import ProductVariant

from .models import Order, OrderItem

logger = logging.getLogger(__name__)


class OutOfStock(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Some items are no longer available in the requested quantity."
    default_code = "out_of_stock"


def shipping_for(subtotal: int) -> int:
    return 0 if subtotal == 0 or subtotal >= settings.FREE_SHIPPING_OVER else settings.SHIPPING_FEE


@transaction.atomic
def create_order(user, address: dict, lines: list[dict]) -> Order:
    """Create a PENDING order. This service is the source of truth, so it re-checks
    stock and uses ITS OWN prices (never trusts prices sent by another service)."""
    variant_ids = [line["variant_id"] for line in lines]
    variants = {
        v.id: v
        # select_for_update locks these rows until the transaction ends, so two
        # simultaneous checkouts can't both buy the last item
        for v in ProductVariant.objects.select_related("product")
        .select_for_update(of=("self",))
        .filter(id__in=variant_ids)
    }

    resolved = []
    for line in lines:
        variant = variants.get(line["variant_id"])
        if variant is None or not variant.product.is_active:
            raise OutOfStock(f"Product variant {line['variant_id']} is no longer available.")
        if variant.stock < line["quantity"]:
            raise OutOfStock(
                f"{variant.product.name} ({variant.color} / {variant.size}) is no longer available "
                f"in that quantity. Only {variant.stock} left."
            )
        resolved.append((variant, line["quantity"]))

    subtotal = sum(v.price * qty for v, qty in resolved)
    shipping_fee = shipping_for(subtotal)
    order = Order.objects.create(
        user=user, subtotal=subtotal, shipping_fee=shipping_fee, total=subtotal + shipping_fee, **address
    )
    OrderItem.objects.bulk_create(
        OrderItem(
            order=order,
            variant=v,
            product_name=v.product.name,
            product_slug=v.product.slug,
            size=v.size,
            color=v.color,
            color_hex=v.color_hex,
            quantity=qty,
            unit_price=v.price,
        )
        for v, qty in resolved
    )
    logger.info("Created order #%s for user %s, total %s", order.id, user.id, order.total)
    return order


@transaction.atomic
def mark_order_paid(order_id: int) -> Order | None:
    """Called when the 'payment.succeeded' event arrives. Idempotent: running it
    twice for the same order changes nothing the second time."""
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        logger.warning("payment.succeeded for unknown order #%s - ignored", order_id)
        return None
    if order.status != Order.Status.PENDING:
        logger.info("Order #%s already %s - nothing to do", order_id, order.status)
        return order

    for item in order.items.all():
        ProductVariant.objects.filter(pk=item.variant_id).update(stock=Greatest(F("stock") - item.quantity, 0))
    order.status = Order.Status.PAID
    order.save(update_fields=["status", "updated_at"])
    logger.info("Order #%s marked PAID and stock reduced", order_id)
    return order

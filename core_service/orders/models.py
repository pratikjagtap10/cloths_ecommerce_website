from django.conf import settings
from django.db import models
from django.utils import timezone

from catalog.models import ProductVariant


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending payment"
        PAID = "PAID", "Paid"
        SHIPPED = "SHIPPED", "Shipped"
        CANCELLED = "CANCELLED", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="orders", on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    subtotal = models.PositiveIntegerField()
    shipping_fee = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField()

    # Shipping address (copied onto the order so later profile edits don't change history)
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    line1 = models.CharField(max_length=200)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    postal_code = models.CharField(max_length=10)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Order #{self.id} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, related_name="order_items", on_delete=models.PROTECT)
    # Snapshot of the product at purchase time (names/prices may change later)
    product_name = models.CharField(max_length=150)
    product_slug = models.CharField(max_length=150)
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=30)
    color_hex = models.CharField(max_length=7)
    quantity = models.PositiveIntegerField()
    unit_price = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]

    @property
    def line_total(self) -> int:
        return self.unit_price * self.quantity

from django.db import models
from django.utils import timezone


class Category(models.Model):
    """Self-referencing tree: Men -> T-Shirts, Women -> Dresses ..."""

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="children", on_delete=models.CASCADE
    )

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "categories"

    def __str__(self):
        return f"{self.parent.name} > {self.name}" if self.parent_id else self.name


class Product(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT)
    # Prices are whole rupees (INR) stored as integers -> no float rounding issues
    base_price = models.PositiveIntegerField(help_text="Price in INR (whole rupees)")
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["is_active", "is_featured"])]

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    """One sellable item: a product in a specific size + colour, with its own stock."""

    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE)
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=30)
    color_hex = models.CharField(max_length=7, default="#cccccc")
    sku = models.CharField(max_length=40, unique=True)
    stock = models.PositiveIntegerField(default=0)
    price_override = models.PositiveIntegerField(
        null=True, blank=True, help_text="Leave empty to use the product's base price"
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "size", "color"], name="unique_variant_per_product")
        ]

    @property
    def price(self) -> int:
        return self.price_override if self.price_override is not None else self.product.base_price

    def __str__(self):
        return f"{self.product.name} ({self.color} / {self.size})"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    url = models.URLField()
    alt_text = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["id"]

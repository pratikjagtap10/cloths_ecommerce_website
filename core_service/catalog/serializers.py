from rest_framework import serializers

from .models import Category, Product, ProductImage, ProductVariant


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent"]


class CategoryRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


class ProductVariantSerializer(serializers.ModelSerializer):
    price = serializers.IntegerField(read_only=True)  # computed property

    class Meta:
        model = ProductVariant
        fields = ["id", "size", "color", "color_hex", "sku", "stock", "price"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "url", "alt_text"]


class ProductSerializer(serializers.ModelSerializer):
    """Nested serializer: one product with its category, variants and images.
    The JSON shape matches frontend/src/types/index.ts -> Product."""

    category = CategoryRefSerializer(read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "description", "category", "base_price",
            "is_active", "is_featured", "created_at", "images", "variants",
        ]


class InternalVariantSerializer(serializers.ModelSerializer):
    """What the shop service needs to put a variant in a cart."""

    price = serializers.IntegerField(read_only=True)
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    is_active = serializers.BooleanField(source="product.is_active", read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id", "product_id", "product_name", "product_slug", "size", "color",
            "color_hex", "sku", "price", "stock", "is_active",
        ]

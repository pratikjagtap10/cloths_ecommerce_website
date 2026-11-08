from django.contrib import admin

from .models import Category, Product, ProductImage, ProductVariant


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "parent"]
    list_filter = ["parent"]
    prepopulated_fields = {"slug": ("name",)}


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ["size", "color", "color_hex", "sku", "stock", "price_override"]


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "base_price", "total_stock", "is_active", "is_featured", "created_at"]
    list_filter = ["is_active", "is_featured", "category"]
    list_editable = ["is_active", "is_featured"]
    search_fields = ["name", "description", "variants__sku"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductVariantInline, ProductImageInline]

    @admin.display(description="Stock")
    def total_stock(self, obj):
        return sum(v.stock for v in obj.variants.all())

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("category").prefetch_related("variants")


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ["sku", "product", "size", "color", "stock", "price"]
    list_filter = ["size", "color"]
    list_editable = ["stock"]
    search_fields = ["sku", "product__name"]

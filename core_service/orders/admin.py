from django.contrib import admin, messages

from events.bus import publish

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ["variant", "product_name", "size", "color", "quantity", "unit_price"]
    fields = readonly_fields


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "total", "city", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["id", "user__email", "full_name", "phone"]
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
    # Status changes go through the actions below so events are always published
    readonly_fields = ["user", "status", "subtotal", "shipping_fee", "total", "created_at", "updated_at"]
    actions = ["mark_shipped", "mark_cancelled"]

    @admin.action(description="Mark selected PAID orders as SHIPPED (publishes order.shipped)")
    def mark_shipped(self, request, queryset):
        count = 0
        for order in queryset.filter(status=Order.Status.PAID).select_related("user"):
            order.status = Order.Status.SHIPPED
            order.save(update_fields=["status", "updated_at"])
            publish("order.shipped", {"order_id": order.id, "user_id": order.user_id, "email": order.user.email})
            count += 1
        self.message_user(request, f"{count} order(s) marked as shipped.", messages.SUCCESS)

    @admin.action(description="Cancel selected PENDING orders")
    def mark_cancelled(self, request, queryset):
        count = queryset.filter(status=Order.Status.PENDING).update(status=Order.Status.CANCELLED)
        self.message_user(request, f"{count} order(s) cancelled.", messages.SUCCESS)

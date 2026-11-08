from rest_framework import serializers

from .models import Order, OrderItem


class AddressSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=100, min_length=2)
    phone = serializers.RegexField(r"^[6-9]\d{9}$", error_messages={"invalid": "Enter a valid 10-digit mobile number."})
    line1 = serializers.CharField(max_length=200, min_length=5)
    city = serializers.CharField(max_length=80, min_length=2)
    state = serializers.CharField(max_length=80, min_length=2)
    postal_code = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "PIN code must be 6 digits."})


class OrderItemSerializer(serializers.ModelSerializer):
    variant_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id", "variant_id", "product_name", "product_slug", "size", "color",
            "color_hex", "quantity", "unit_price",
        ]


class OrderSerializer(serializers.ModelSerializer):
    """Shape matches frontend/src/types/index.ts -> Order."""

    user_id = serializers.IntegerField(read_only=True)
    # source="*" builds the nested "address" object from flat columns on Order
    address = AddressSerializer(source="*", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "user_id", "status", "subtotal", "total", "shipping_fee", "address", "created_at", "items"]


# ---------- internal API (shop service -> core service) ----------
class OrderLineInputSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=20)


class InternalOrderCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)
    address = AddressSerializer()
    items = OrderLineInputSerializer(many=True, allow_empty=False)

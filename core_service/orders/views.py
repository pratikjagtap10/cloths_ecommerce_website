from django.shortcuts import get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import HasInternalApiKey
from users.models import User

from .models import Order
from .serializers import InternalOrderCreateSerializer, OrderSerializer
from .services import create_order, create_order_idempotent


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/core/orders/        -> the logged-in user's orders (newest first)
    GET /api/core/orders/{id}/   -> one order

    Object-level security: the queryset only contains the current user's orders,
    so asking for someone else's order id returns 404 (not even 403, which would
    reveal that the order exists).
    """

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items")


class InternalOrderCreateView(generics.GenericAPIView):
    """POST /internal/orders/  (shop service only, needs X-Internal-Key)

    Body: {"user_id": 1, "address": {...}, "items": [{"variant_id": 2, "quantity": 1}],
           "idempotency_key": "optional-unique-key"}

    With an idempotency_key, a repeated request returns the ORIGINAL order with
    200 (instead of 201) and the header "Idempotent-Replayed: true".
    """

    serializer_class = InternalOrderCreateSerializer
    permission_classes = [HasInternalApiKey]
    authentication_classes: list = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = get_object_or_404(User, pk=data["user_id"], is_active=True)
        address = dict(data["address"])
        lines = [dict(line) for line in data["items"]]

        key = data.get("idempotency_key")
        if not key:
            order = create_order(user, address, lines)
            return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

        order, created = create_order_idempotent(user, address, lines, key)
        if created:
            return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK, headers={"Idempotent-Replayed": "true"})

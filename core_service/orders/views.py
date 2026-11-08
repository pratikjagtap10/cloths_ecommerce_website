from django.shortcuts import get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import HasInternalApiKey
from users.models import User

from .models import Order
from .serializers import InternalOrderCreateSerializer, OrderSerializer
from .services import create_order


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

    Body: {"user_id": 1, "address": {...}, "items": [{"variant_id": 2, "quantity": 1}]}
    """

    serializer_class = InternalOrderCreateSerializer
    permission_classes = [HasInternalApiKey]
    authentication_classes: list = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = get_object_or_404(User, pk=data["user_id"], is_active=True)
        order = create_order(user, dict(data["address"]), [dict(line) for line in data["items"]])
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

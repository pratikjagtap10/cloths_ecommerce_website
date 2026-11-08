from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, viewsets
from rest_framework.filters import SearchFilter
from rest_framework.permissions import AllowAny

from core.permissions import HasInternalApiKey

from .filters import AliasOrderingFilter, ProductFilter
from .models import Category, Product, ProductVariant
from .serializers import CategorySerializer, InternalVariantSerializer, ProductSerializer


class CategoryListView(generics.ListAPIView):
    """GET /api/core/categories/  -> full list (not paginated, it is small)"""

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []
    pagination_class = None


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/core/products/          list  (filter, search, sort, paginate)
    GET /api/core/products/{slug}/   detail
    """

    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, SearchFilter, AliasOrderingFilter]
    filterset_class = ProductFilter
    search_fields = ["name", "description"]
    ordering_fields = ["base_price", "name", "created_at"]
    ordering = ["-created_at", "id"]

    def get_queryset(self):
        # select_related / prefetch_related avoid the "N+1 queries" problem
        return (
            Product.objects.filter(is_active=True)
            .select_related("category")
            .prefetch_related("variants", "images")
        )

    def filter_queryset(self, queryset):
        # Filtering through variants (size/colour) joins rows -> remove duplicates
        return super().filter_queryset(queryset).distinct()


class InternalVariantView(generics.RetrieveAPIView):
    """GET /internal/variants/{id}/  (shop service only, needs X-Internal-Key)"""

    serializer_class = InternalVariantSerializer
    permission_classes = [HasInternalApiKey]
    authentication_classes: list = []

    def get_object(self):
        return get_object_or_404(ProductVariant.objects.select_related("product"), pk=self.kwargs["pk"])

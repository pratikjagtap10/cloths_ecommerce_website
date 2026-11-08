from django.db.models import Q
from django_filters import rest_framework as filters
from rest_framework.filters import OrderingFilter

from .models import Product


class ProductFilter(filters.FilterSet):
    """Query-string filters: /products/?category=men&size=M&color=Black&min_price=500"""

    category = filters.CharFilter(method="filter_category")
    size = filters.CharFilter(field_name="variants__size", lookup_expr="iexact")
    color = filters.CharFilter(field_name="variants__color", lookup_expr="iexact")
    min_price = filters.NumberFilter(field_name="base_price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="base_price", lookup_expr="lte")
    featured = filters.BooleanFilter(field_name="is_featured")

    class Meta:
        model = Product
        fields = ["category", "size", "color", "min_price", "max_price", "featured"]

    def filter_category(self, queryset, name, value):
        # A parent category (e.g. "men") also includes its children ("men-tshirts"...)
        return queryset.filter(Q(category__slug=value) | Q(category__parent__slug=value))


class AliasOrderingFilter(OrderingFilter):
    """Lets clients use friendly names: ?ordering=price  -> ORDER BY base_price."""

    aliases = {"price": "base_price"}

    def get_ordering(self, request, queryset, view):
        raw = request.query_params.get(self.ordering_param)
        if raw:
            allowed = set(view.ordering_fields)
            fields = []
            for term in raw.split(","):
                term = term.strip()
                desc = term.startswith("-")
                name = self.aliases.get(term.lstrip("-"), term.lstrip("-"))
                if name in allowed:
                    fields.append(f"-{name}" if desc else name)
            if fields:
                return [*fields, "id"]  # "id" makes pagination order stable
        return self.get_default_ordering(view)

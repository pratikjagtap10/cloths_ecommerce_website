from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CategoryListView, ProductViewSet

router = DefaultRouter()
router.include_root_view = False
router.register("products", ProductViewSet, basename="product")

urlpatterns = [
    path("categories/", CategoryListView.as_view(), name="category-list"),
    *router.urls,
]

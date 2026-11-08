from rest_framework.routers import DefaultRouter

from .views import OrderViewSet

router = DefaultRouter()
router.include_root_view = False
router.register("orders", OrderViewSet, basename="order")

urlpatterns = router.urls

from django.contrib import admin
from django.urls import include, path

from catalog.views import InternalVariantView
from orders.views import InternalOrderCreateView

from .views import health

admin.site.site_header = "Threads Store Admin"
admin.site.site_title = "Threads Admin"
admin.site.index_title = "Store management"

# Public API (reached through Nginx at http://localhost/api/core/...)
public_api = [
    path("health/", health, name="health"),
    path("auth/", include("users.urls")),
    path("", include("catalog.urls")),
    path("", include("orders.urls")),
]

# Internal API: only for other microservices (blocked by Nginx)
internal_api = [
    path("variants/<int:pk>/", InternalVariantView.as_view(), name="internal-variant"),
    path("orders/", InternalOrderCreateView.as_view(), name="internal-order-create"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/core/", include(public_api)),
    path("internal/", include(internal_api)),
]

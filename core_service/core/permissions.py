import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasInternalApiKey(BasePermission):
    """
    Service-to-service authentication.

    Internal endpoints (/internal/...) are called by other microservices, never by
    browsers. The caller must send the shared secret in the `X-Internal-Key` header.
    Nginx also blocks /internal/ so these URLs are not reachable from outside Docker.
    """

    message = "Missing or invalid internal API key."

    def has_permission(self, request, view):
        provided = request.headers.get("X-Internal-Key", "")
        return hmac.compare_digest(provided, settings.INTERNAL_API_KEY)

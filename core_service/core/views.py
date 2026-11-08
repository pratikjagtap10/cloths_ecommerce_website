from django.db import connection
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Used by Docker health checks and for quick manual checks."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database = "ok"
    except Exception:  # noqa: BLE001
        database = "unavailable"
    status = 200 if database == "ok" else 503
    return Response({"status": "ok" if status == 200 else "degraded", "service": "core", "database": database}, status=status)

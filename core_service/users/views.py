from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import LoginSerializer, RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    """POST /api/core/auth/register/  -> 201 {id, email, first_name, last_name}"""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []


class LoginView(TokenObtainPairView):
    """POST /api/core/auth/login/  {email, password} -> {access, refresh}"""

    serializer_class = LoginSerializer


class RefreshView(TokenRefreshView):
    """POST /api/core/auth/refresh/  {refresh} -> {access}"""


class MeView(generics.RetrieveAPIView):
    """GET /api/core/auth/me/  (needs Authorization: Bearer <access>)"""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

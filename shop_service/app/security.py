"""
JWT verification. The token was issued by the Django core service; this service
only VERIFIES it using the shared secret, so it never needs to call Django to
find out who the user is (stateless authentication).
"""
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: int
    email: str | None = None
    first_name: str | None = None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Please log in to continue.")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Session expired. Please log in again.") from None
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid authentication token.") from None

    if payload.get("token_type") != "access" or "user_id" not in payload:
        raise _unauthorized("Invalid authentication token.")
    return CurrentUser(id=int(payload["user_id"]), email=payload.get("email"), first_name=payload.get("first_name"))

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.models.enums import UserRole
from app.schemas.auth import AuthenticatedUser

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None:
        raise UnauthorizedError("Authentication credentials were not provided")

    try:
        payload = decode_access_token(credentials.credentials)
        if payload.get("type") != "access":
            raise UnauthorizedError("Invalid token type")
        current_user = AuthenticatedUser(
            id=int(payload["sub"]),
            email=str(payload["email"]),
            first_name=payload.get("first_name"),
            last_name=payload.get("last_name"),
            role=str(payload["role"]),
            is_superadmin=bool(payload.get("is_superadmin", False)),
            is_active=bool(payload.get("is_active", False)),
            is_verified=bool(payload.get("is_verified", False)),
            last_login_at=payload.get("last_login_at"),
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
        )
    except Exception as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc

    if not current_user.is_active:
        raise UnauthorizedError("User is not authorized")

    return current_user


def require_admin(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if current_user.role != UserRole.ADMIN.value:
        raise ForbiddenError("Admin access is required")
    return current_user


def require_superadmin(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if current_user.role != UserRole.ADMIN.value or not current_user.is_superadmin:
        raise ForbiddenError("Superadmin access is required")
    return current_user

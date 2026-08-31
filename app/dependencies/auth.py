from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user import UserRepository
from app.dependencies.providers import get_user_repository

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    repository: UserRepository = Depends(get_user_repository),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Authentication credentials were not provided")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except Exception as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc

    user = repository.get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User is not authorized")

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenError("Admin access is required")
    return current_user


def require_superadmin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN or not current_user.is_superadmin:
        raise ForbiddenError("Superadmin access is required")
    return current_user

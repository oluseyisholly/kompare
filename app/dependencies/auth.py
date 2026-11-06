from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token, has_legacy_bootstrap_password
from app.models.enums import AdminType, UserRole
from app.models.user import User
from app.schemas.auth import AuthenticatedUser

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    if credentials is None:
        raise UnauthorizedError("Authentication credentials were not provided")

    try:
        payload = decode_access_token(credentials.credentials)
        if payload.get("type") != "access":
            raise UnauthorizedError("Invalid token type")
        user = (
            db.query(User).filter(User.id == int(payload["sub"])).populate_existing().one_or_none()
        )
        if (
            user is None
            or not user.is_active
            or user.status.value in {"suspended", "deleted"}
            or has_legacy_bootstrap_password(user.password_hash)
            or payload.get("auth_version", 0) != user.auth_version
        ):
            raise UnauthorizedError("User is not authorized")
        current_user = AuthenticatedUser(
            **{field: getattr(user, field) for field in AuthenticatedUser.model_fields}
        )
    except Exception as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc

    if not current_user.is_active:
        raise UnauthorizedError("User is not authorized")

    return current_user


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedUser | None:
    if credentials is None:
        return None
    return get_current_user(credentials, db)


def require_admin(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    allowed_admin_types = {AdminType.SUPER_ADMIN.value, AdminType.SUPPORT_ADMIN.value}
    if (
        current_user.role != UserRole.ADMIN.value
        or current_user.admin_type not in allowed_admin_types
    ):
        raise ForbiddenError("Admin access is required")
    return current_user


def require_superadmin(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    if (
        current_user.role != UserRole.ADMIN.value
        or current_user.admin_type != AdminType.SUPER_ADMIN.value
    ):
        raise ForbiddenError("Superadmin access is required")
    return current_user

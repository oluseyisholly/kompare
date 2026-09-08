from __future__ import annotations

import secrets
from datetime import UTC, datetime

from app.core.exceptions import BadRequestError, NotFoundError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_token,
    verify_password,
    verify_token_hash,
)
from app.models.enums import UserRole
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.auth import (
    AdminRegisterRequest,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    UserRead,
    UserRegisterRequest,
)


class AuthService:
    def __init__(
        self,
        repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
    ) -> None:
        self.repository = repository
        self.refresh_token_repository = refresh_token_repository

    def register_user(self, payload: UserRegisterRequest) -> UserRead:
        return self._create_user(
            email=payload.email,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            role=UserRole.USER,
            is_superadmin=False,
        )

    def register_admin(self, payload: AdminRegisterRequest) -> UserRead:
        return self._create_user(
            email=payload.email,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            role=UserRole.ADMIN,
            is_superadmin=False,
        )

    def _create_user(
        self,
        *,
        email: str,
        password: str,
        first_name: str | None,
        last_name: str | None,
        role: UserRole,
        is_superadmin: bool,
    ) -> UserRead:
        if self.repository.get_by_email(email) is not None:
            raise BadRequestError(
                "A user with this email already exists",
                data={"email": email},
            )

        user = self.repository.create(
            User(
                email=email.lower(),
                password_hash=hash_password(password),
                first_name=first_name,
                last_name=last_name,
                role=role,
                is_superadmin=is_superadmin,
            )
        )
        return self._to_schema(user)

    def login(self, payload: LoginRequest) -> LoginResponse:
        user = self.repository.get_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise UnauthorizedError("Invalid email or password")
        if not user.is_active:
            raise UnauthorizedError("User account is inactive")

        user = self.repository.mark_login(user)
        access_token = self._build_access_token(user)
        refresh_token = self._issue_refresh_token(user)
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=self._to_schema(user),
        )

    def refresh(self, payload: RefreshTokenRequest) -> LoginResponse:
        try:
            token_payload = decode_access_token(payload.refresh_token)
        except Exception as exc:
            raise UnauthorizedError("Invalid or expired refresh token") from exc

        if token_payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token type")

        token_id = token_payload.get("jti")
        subject = token_payload.get("sub")
        if not token_id or not subject:
            raise UnauthorizedError("Invalid refresh token payload")

        stored_token = self.refresh_token_repository.get_active_by_token_id(str(token_id))
        if stored_token is None:
            raise UnauthorizedError("Refresh token is no longer valid")

        if not verify_token_hash(payload.refresh_token, stored_token.token_hash):
            raise UnauthorizedError("Refresh token verification failed")

        if stored_token.expires_at <= datetime.now(UTC):
            self.refresh_token_repository.revoke(stored_token)
            raise UnauthorizedError("Refresh token has expired")

        user = self.repository.get_by_id(int(subject))
        if user is None:
            self.refresh_token_repository.revoke(stored_token)
            raise UnauthorizedError("User not found for refresh token")
        if not user.is_active:
            self.refresh_token_repository.revoke(stored_token)
            raise UnauthorizedError("User account is inactive")

        self.refresh_token_repository.revoke(stored_token)

        access_token = self._build_access_token(user)
        refresh_token = self._issue_refresh_token(user)
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=self._to_schema(user),
        )

    def logout(self, payload: RefreshTokenRequest) -> None:
        try:
            token_payload = decode_access_token(payload.refresh_token)
        except Exception as exc:
            raise UnauthorizedError("Invalid or expired refresh token") from exc

        if token_payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token type")

        token_id = token_payload.get("jti")
        if not token_id:
            raise UnauthorizedError("Invalid refresh token payload")

        stored_token = self.refresh_token_repository.get_active_by_token_id(str(token_id))
        if stored_token is None:
            return

        if verify_token_hash(payload.refresh_token, stored_token.token_hash):
            self.refresh_token_repository.revoke(stored_token)

    def _build_access_token(self, user: User) -> str:
        token = create_access_token(
            subject=str(user.id),
            email=user.email,
            role=user.role.value,
            is_superadmin=user.is_superadmin,
            is_active=user.is_active,
            is_verified=user.is_verified,
            first_name=user.first_name,
            last_name=user.last_name,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        return token

    def _issue_refresh_token(self, user: User) -> str:
        token_id = secrets.token_urlsafe(32)
        refresh_token, expires_at = create_refresh_token(
            subject=str(user.id),
            token_id=token_id,
        )
        self.refresh_token_repository.create(
            RefreshToken(
                user_id=user.id,
                token_id=token_id,
                token_hash=hash_token(refresh_token),
                expires_at=expires_at,
            )
        )
        return refresh_token

    def get_user_by_id(self, user_id: int) -> User:
        user = self.repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found", data={"user_id": user_id})
        return user

    @staticmethod
    def _to_schema(user: User) -> UserRead:
        return UserRead(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role.value,
            is_superadmin=user.is_superadmin,
            is_active=user.is_active,
            is_verified=user.is_verified,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

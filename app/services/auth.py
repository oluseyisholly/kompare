from __future__ import annotations

from app.core.exceptions import BadRequestError, NotFoundError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import AdminRegisterRequest, LoginRequest, LoginResponse, UserRead, UserRegisterRequest


class AuthService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

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
        token = create_access_token(subject=str(user.id), role=user.role.value)
        return LoginResponse(
            access_token=token,
            user=self._to_schema(user),
        )

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

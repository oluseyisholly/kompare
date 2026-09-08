from fastapi import APIRouter, Depends

from app.dependencies import get_auth_service
from app.dependencies.auth import get_current_user, require_superadmin
from app.schemas.auth import (
    AdminRegisterRequest,
    AuthenticatedUser,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    UserRead,
    UserRegisterRequest,
)
from app.schemas.common import ApiResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ApiResponse[UserRead], status_code=201)
def register(
    payload: UserRegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[UserRead]:
    return ApiResponse(
        responseCode=201,
        message="User onboarded successfully",
        data=service.register_user(payload),
    )


@router.post("/admins", response_model=ApiResponse[UserRead], status_code=201)
def register_admin(
    payload: AdminRegisterRequest,
    service: AuthService = Depends(get_auth_service),
    current_user: AuthenticatedUser = Depends(require_superadmin),
) -> ApiResponse[UserRead]:
    del current_user
    return ApiResponse(
        responseCode=201,
        message="Admin created successfully",
        data=service.register_admin(payload),
    )


@router.post("/login", response_model=ApiResponse[LoginResponse])
def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[LoginResponse]:
    return ApiResponse(
        responseCode=200,
        message="Login successful",
        data=service.login(payload),
    )


@router.post("/refresh", response_model=ApiResponse[LoginResponse])
def refresh_token(
    payload: RefreshTokenRequest,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[LoginResponse]:
    return ApiResponse(
        responseCode=200,
        message="Token refreshed successfully",
        data=service.refresh(payload),
    )


@router.post("/logout", response_model=ApiResponse[dict[str, str]])
def logout(
    payload: RefreshTokenRequest,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[dict[str, str]]:
    service.logout(payload)
    return ApiResponse(
        responseCode=200,
        message="Logout successful",
        data={"status": "logged_out"},
    )


@router.get("/me", response_model=ApiResponse[UserRead])
def get_me(current_user: AuthenticatedUser = Depends(get_current_user)) -> ApiResponse[UserRead]:
    return ApiResponse(
        responseCode=200,
        message="Authenticated user retrieved successfully",
        data=UserRead(
            id=current_user.id,
            email=current_user.email,
            first_name=current_user.first_name,
            last_name=current_user.last_name,
            role=current_user.role,
            is_superadmin=current_user.is_superadmin,
            is_active=current_user.is_active,
            is_verified=current_user.is_verified,
            last_login_at=current_user.last_login_at,
            created_at=current_user.created_at,
            updated_at=current_user.updated_at,
        ),
    )
